"""Small additive agent API for the supplied Flask portal.

Mount this blueprint from app/app.py with:
    from agent_api import agent_api
    app.register_blueprint(agent_api, url_prefix="/api/agent")

The MCP services call these routes. The routes do not maintain a second
database; application creation and decisions use the portal's existing
validation, creation and audit helpers.
"""
import base64
import hashlib
import hmac
import json
import os
import time
from functools import wraps

from flask import Blueprint, jsonify, request

import app as portal

agent_api = Blueprint("agent_api", __name__)

INTERNAL_SECRET = os.environ.get("AGENT_INTERNAL_SECRET", "change-this-agent-secret")
ENABLED_BLOCKS = tuple(
    b.strip() for b in os.environ.get(
        "AGENT_ENABLED_BLOCKS",
        "Sonari,Rajapara,Dhemaji Pathar,Borgaon,Namti,Khelua",
    ).split(",") if b.strip()
)

def _principal():
    encoded = request.headers.get("X-SewaSetu-Agent-Principal", "")
    signature = request.headers.get("X-SewaSetu-Agent-Signature", "")
    if not encoded or not signature:
        return None
    expected = hmac.new(
        INTERNAL_SECRET.encode(), encoded.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        p = json.loads(raw)
        if abs(int(time.time()) - int(p["iat"])) > 90:
            return None
        if p.get("role") not in {"citizen", "officer"}:
            return None
        if not str(p.get("sub", "")).strip():
            return None
        return p
    except Exception:
        return None

def require_role(role):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            p = _principal()
            if not p or p.get("role") != role:
                return jsonify({"ok": False, "error": "unauthorized"}), 403
            return fn(p, *args, **kwargs)
        return wrapped
    return decorator

def _app_row(cur, app_id):
    cur.execute(
        """SELECT id, application_no, applicant_name, mobile, dob, gender,
                  marital_status, village, block, bank_account, ifsc, doc_path,
                  status, submitted_at, decided_at, decided_by
           FROM applications WHERE id = %s""",
        (app_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    keys = [
        "id","application_no","applicant_name","mobile","dob","gender",
        "marital_status","village","block","bank_account","ifsc","doc_path",
        "status","submitted_at","decided_at","decided_by"
    ]
    return dict(zip(keys, row))

@agent_api.get("/me")
def me():
    p = _principal()
    if not p:
        return jsonify({"ok": False, "error": "unauthorized"}), 403
    return jsonify({
        "ok": True,
        "subject": p["sub"],
        "role": p["role"],
    })

@agent_api.post("/citizen/eligibility")
@require_role("citizen")
def citizen_eligibility(p):
    data = request.get_json(silent=True) or {}
    has_doc = bool(data.get("has_age_proof", False))
    doc_path = "eligibility-check" if has_doc else ""
    errors, cleaned = portal.validate_application(data, doc_path)

    # Eligibility checking is informational; it must never create an application.
    return jsonify({
        "ok": not errors,
        "eligible": not errors,
        "errors": errors,
        "normalized": {
            k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in cleaned.items() if k != "doc_path"
        },
        "enabled_blocks": list(ENABLED_BLOCKS),
    })

@agent_api.post("/citizen/upload")
@require_role("citizen")
def citizen_upload(p):
    body = request.get_json(silent=True) or {}
    filename = str(body.get("filename", "age-proof.pdf")).strip()
    content_b64 = body.get("content_base64", "")
    if not content_b64:
        return jsonify({"ok": False, "error": "content_base64 is required"}), 400
    if len(content_b64) > 8 * 1024 * 1024:
        return jsonify({"ok": False, "error": "document is too large"}), 400

    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in {"pdf", "jpg", "jpeg", "png"}:
        return jsonify({"ok": False, "error": "only PDF/JPG/JPEG/PNG is allowed"}), 400

    try:
        content = base64.b64decode(content_b64, validate=True)
    except Exception:
        return jsonify({"ok": False, "error": "invalid base64 document"}), 400
    if len(content) > 5 * 1024 * 1024:
        return jsonify({"ok": False, "error": "document is larger than 5 MB"}), 400

    safe_name = os.path.basename(filename).replace(" ", "_")
    upload_dir = portal.UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, f"agent_{p['sub'].split(':',1)[-1]}_{safe_name}")
    with open(path, "wb") as fh:
        fh.write(content)
    return jsonify({"ok": True, "doc_path": path, "filename": safe_name})

@agent_api.post("/citizen/applications")
@require_role("citizen")
def citizen_submit(p):
    data = request.get_json(silent=True) or {}
    block = str(data.get("block", "")).strip()
    if block not in ENABLED_BLOCKS:
        return jsonify({
            "ok": False,
            "error": f"Agent applications are currently enabled only for: {', '.join(ENABLED_BLOCKS)}"
        }), 422

    doc_path = str(data.get("age_proof_path", "")).strip()
    if not doc_path or not os.path.isfile(doc_path):
        return jsonify({"ok": False, "error": "age proof document must be uploaded first"}), 422

    mobile = str(p["sub"]).removeprefix("citizen:")
    errors, cleaned = portal.validate_application(data, doc_path)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 422

    conn = portal.get_db()
    cur = conn.cursor()
    try:
        existing = portal.active_application(cur, mobile)
        if existing:
            return jsonify({
                "ok": False,
                "error": "an active application already exists",
                "application_id": existing[0],
                "application_no": existing[1],
                "status": existing[2],
            }), 409

        new_id, app_no = portal.create_application(cur, mobile, cleaned)
        conn.commit()
        portal.send_sms(
            mobile,
            f"Sewa Setu: application {app_no} received. Track at the status portal."
        )
        return jsonify({
            "ok": True,
            "application_id": new_id,
            "application_no": app_no,
            "status": "PENDING",
        })
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

@agent_api.get("/citizen/application")
@require_role("citizen")
def citizen_application(p):
    mobile = str(p["sub"]).removeprefix("citizen:")
    conn = portal.get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT id, application_no, applicant_name, mobile, dob, village,
                      block, bank_account, ifsc, status, submitted_at,
                      decided_at, decided_by
               FROM applications WHERE mobile = %s
               ORDER BY submitted_at DESC LIMIT 1""",
            (mobile,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"ok": True, "application": None})
        keys = [
            "id","application_no","applicant_name","mobile","dob","village",
            "block","bank_account","ifsc","status","submitted_at","decided_at","decided_by"
        ]
        a = dict(zip(keys, row))
        for k, v in list(a.items()):
            if hasattr(v, "isoformat"):
                a[k] = v.isoformat()
        return jsonify({"ok": True, "application": a})
    finally:
        cur.close()
        conn.close()

@agent_api.post("/citizen/application/withdraw")
@require_role("citizen")
def citizen_withdraw(p):
    mobile = str(p["sub"]).removeprefix("citizen:")
    conn = portal.get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """UPDATE applications
               SET status='WITHDRAWN', decided_at=%s, decided_by='APPLICANT'
               WHERE mobile=%s AND status='PENDING'
               RETURNING id, application_no""",
            (portal.now_ist(), mobile),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"ok": False, "error": "only a pending application can be withdrawn"}), 409
        portal.write_audit(cur, row[0], "WITHDRAW", f"applicant:{mobile}")
        conn.commit()
        return jsonify({"ok": True, "application_id": row[0], "application_no": row[1], "status": "WITHDRAWN"})
    finally:
        cur.close()
        conn.close()

@agent_api.get("/officer/applications")
@require_role("officer")
def officer_applications(p):
    block = request.args.get("block", "").strip()
    if block and block not in ENABLED_BLOCKS:
        return jsonify({"ok": False, "error": "block is not enabled for agent access"}), 403
    try:
        limit = min(max(int(request.args.get("limit", 20)), 1), 50)
    except ValueError:
        limit = 20

    conn = portal.get_db()
    cur = conn.cursor()
    try:
        if block:
            cur.execute(
                """SELECT id, application_no, applicant_name, mobile, village, block,
                          status, submitted_at
                   FROM applications
                   WHERE status='PENDING' AND block=%s
                   ORDER BY submitted_at ASC LIMIT %s""",
                (block, limit),
            )
        else:
            cur.execute(
                """SELECT id, application_no, applicant_name, mobile, village, block,
                          status, submitted_at
                   FROM applications
                   WHERE status='PENDING' AND block = ANY(%s)
                   ORDER BY submitted_at ASC LIMIT %s""",
                (list(ENABLED_BLOCKS), limit),
            )
        rows = cur.fetchall()
        keys = ["id","application_no","applicant_name","mobile","village","block","status","submitted_at"]
        out = []
        for row in rows:
            a = dict(zip(keys, row))
            if hasattr(a["submitted_at"], "isoformat"):
                a["submitted_at"] = a["submitted_at"].isoformat()
            out.append(a)
        return jsonify({"ok": True, "applications": out, "enabled_blocks": list(ENABLED_BLOCKS)})
    finally:
        cur.close()
        conn.close()

@agent_api.get("/officer/applications/<int:app_id>")
@require_role("officer")
def officer_application(p, app_id):
    conn = portal.get_db()
    cur = conn.cursor()
    try:
        a = _app_row(cur, app_id)
        if not a or a["block"] not in ENABLED_BLOCKS:
            return jsonify({"ok": False, "error": "application not available through agent access"}), 404
        cur.execute(
            "SELECT at, action, actor, note FROM audit_log WHERE application_id=%s ORDER BY at ASC",
            (app_id,),
        )
        audit = []
        for at, action, actor, note in cur.fetchall():
            audit.append({
                "at": at.isoformat() if hasattr(at, "isoformat") else at,
                "action": action, "actor": actor, "note": note,
            })
        for k, v in list(a.items()):
            if hasattr(v, "isoformat"):
                a[k] = v.isoformat()
        # Do not expose the stored document path to the officer model.
        a.pop("doc_path", None)
        return jsonify({"ok": True, "application": a, "audit": audit})
    finally:
        cur.close()
        conn.close()

@agent_api.post("/officer/applications/<int:app_id>/decision")
@require_role("officer")
def officer_decision(p, app_id):
    body = request.get_json(silent=True) or {}
    decision = str(body.get("decision", "")).strip().upper()
    reason = str(body.get("reason", "")).strip()
    if decision not in {"APPROVED", "REJECTED"}:
        return jsonify({"ok": False, "error": "decision must be APPROVED or REJECTED"}), 422
    if not reason:
        return jsonify({"ok": False, "error": "reason is required"}), 422

    conn = portal.get_db()
    cur = conn.cursor()
    try:
        a = _app_row(cur, app_id)
        if not a or a["block"] not in ENABLED_BLOCKS:
            return jsonify({"ok": False, "error": "application not available through agent access"}), 404
        actor = str(p["sub"]).removeprefix("officer:")
        cur.execute(
            """UPDATE applications
               SET status=%s, decided_at=%s, decided_by=%s
               WHERE id=%s AND status='PENDING'
               RETURNING application_no, status, decided_at, decided_by""",
            (decision, portal.now_ist(), actor, app_id),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"ok": False, "error": "only a pending application can be decided"}), 409
        portal.write_audit(
            cur, app_id, decision, f"admin:{actor}", reason
        )
        conn.commit()
        return jsonify({
            "ok": True,
            "application_no": row[0],
            "status": row[1],
            "decided_at": row[2].isoformat(),
            "decided_by": row[3],
            "reason": reason,
        })
    finally:
        cur.close()
        conn.close()
