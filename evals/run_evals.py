"""End-to-end Sewa Setu MCP evaluation runner.

This is a real MCP client: it connects to the running Citizen and Officer
Streamable HTTP servers, calls their tools, and then verifies PostgreSQL state.
It uses short-lived evaluation JWTs signed with the portal's existing OAuth key;
no application data is written directly by the evaluator.
"""
import asyncio
import base64
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import jwt
import psycopg2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from checks import (
    check_application_by_mobile,
    check_decision,
    check_no_application_for_mobile,
)

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
CITIZEN_MCP_URL = os.environ.get("CITIZEN_MCP_URL", "http://localhost:8101/").rstrip("/")
OFFICER_MCP_URL = os.environ.get("OFFICER_MCP_URL", "http://localhost:8102/").rstrip("/")
DB_HOST = os.environ.get("DB_HOST", "db")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "sewasetu")
DB_USER = os.environ.get("DB_USER", "sewasetu")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "sewasetu123")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")


def load_personas():
    return json.loads((ROOT / "personas.json").read_text())


def db():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def portal_signing_key():
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "SELECT private_pem FROM oauth_keys ORDER BY created_at ASC LIMIT 1"
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise RuntimeError("Portal OAuth signing key does not exist yet. Complete one OAuth sign-in first.")
    return row[0]


def eval_token(subject, role, audience):
    now = int(time.time())
    claims = {
        "iss": PUBLIC_BASE_URL,
        "sub": subject,
        "aud": audience,
        "scope": role,
        "role": role,
        "client_id": "sewa-setu-evals",
        "iat": now,
        "exp": now + 600,
        "jti": f"eval-{role}-{now}-{abs(hash(subject))}",
        "kind": "evaluation",
    }
    return jwt.encode(claims, portal_signing_key(), algorithm="RS256")


def text_result(result):
    out = []
    for item in getattr(result, "content", []) or []:
        value = getattr(item, "text", None)
        if value is not None:
            out.append(value)
    if out:
        joined = "\n".join(out)
        try:
            return json.loads(joined)
        except Exception:
            return joined
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured
    return str(result)


async def call_tool(session, name, arguments=None):
    result = await session.call_tool(name, arguments=arguments or {})
    return text_result(result)


async def citizen_case(persona):
    token = eval_token(
        "citizen:" + persona["mobile"],
        "citizen",
        CITIZEN_MCP_URL,
    )
    transcript = []

    async with streamable_http_client(
        os.environ.get("EVAL_CITIZEN_CONNECT_URL", "http://citizen-mcp:8101/")
    , headers={"Authorization": f"Bearer {token}"}) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            me = await call_tool(session, "who_am_i")
            transcript.append({"tool": "who_am_i", "result": me})

            p = persona
            eligibility = await call_tool(
                session,
                "check_pension_eligibility",
                {
                    "applicant_name": p["name"],
                    "dob": p["dob"],
                    "village": p["village"],
                    "block": p["block"],
                    "bank_account": p["bank_account"],
                    "ifsc": p["ifsc"],
                    "has_age_proof": p["id"] not in {
                        "missing_age_proof_sonari_kamla_devi"
                    },
                },
            )
            transcript.append({"tool": "check_pension_eligibility", "result": eligibility})

            should_apply = bool(p["expected_db"].get("application_created"))
            upload_result = None
            submit_result = None

            if should_apply or p["id"] not in {
                "wrong_block_dhemaji_pathar",
                "missing_age_proof_sonari_kamla_devi",
            }:
                if p["id"] != "missing_age_proof_sonari_kamla_devi":
                    fake_pdf = base64.b64encode(
                        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
                    ).decode()
                    upload_result = await call_tool(
                        session,
                        "upload_age_proof",
                        {
                            "filename": "age-proof.pdf",
                            "content_base64": fake_pdf,
                        },
                    )
                    transcript.append({"tool": "upload_age_proof", "result": upload_result})

            doc_path = ""
            if isinstance(upload_result, dict):
                doc_path = upload_result.get("doc_path", "")

            submit_result = await call_tool(
                session,
                "apply_for_pension",
                {
                    "applicant_name": p["name"],
                    "dob": p["dob"],
                    "village": p["village"],
                    "block": p["block"],
                    "bank_account": p["bank_account"],
                    "ifsc": p["ifsc"],
                    "age_proof_path": doc_path,
                },
            )
            transcript.append({"tool": "apply_for_pension", "result": submit_result})

            latest = await call_tool(session, "get_my_application")
            transcript.append({"tool": "get_my_application", "result": latest})

    conn = db()
    expected = p["expected_db"]
    if expected.get("application_created"):
        checks = check_application_by_mobile(
            conn,
            p["mobile"],
            {
                "applicant_name": expected["applicant_name"],
                "mobile": expected["mobile"],
                "block": expected["block"],
                "status": expected["status"],
            },
        )
    else:
        checks = check_no_application_for_mobile(conn, p["mobile"])
    conn.close()

    return checks, transcript


async def officer_followup(persona):
    token = eval_token(
        "officer:" + ADMIN_USERNAME,
        "officer",
        OFFICER_MCP_URL,
    )
    transcript = []

    async with streamable_http_client(
        os.environ.get("EVAL_OFFICER_CONNECT_URL", "http://officer-mcp:8102/")
    , headers={"Authorization": f"Bearer {token}"}) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            identity = await call_tool(session, "officer_identity")
            queue = await call_tool(
                session,
                "list_pending_applications",
                {"block": persona["block"], "limit": 20},
            )
            transcript.extend([
                {"tool": "officer_identity", "result": identity},
                {"tool": "list_pending_applications", "result": queue},
            ])

            applications = queue.get("applications", []) if isinstance(queue, dict) else []
            target = next(
                (a for a in applications if a.get("mobile") == persona["mobile"]),
                None,
            )
            if not target:
                return (
                    {"passed": False, "checks": {"officer_found_application": False},
                     "actual": applications},
                    transcript,
                )

            detail = await call_tool(
                session, "get_application", {"application_id": target["id"]}
            )
            transcript.append({"tool": "get_application", "result": detail})

            decision = await call_tool(
                session,
                "decide_application",
                {
                    "application_id": target["id"],
                    "decision": "APPROVED",
                    "reason": "Evaluation case: valid age, enabled block, required details and age proof present.",
                },
            )
            transcript.append({"tool": "decide_application", "result": decision})

    conn = db()
    checks = check_decision(
        conn,
        persona["mobile"],
        "APPROVED",
        ADMIN_USERNAME,
    )
    conn.close()
    return checks, transcript


async def run():
    personas = load_personas()
    summary = []

    for persona in personas:
        started = datetime.now(timezone.utc).isoformat()
        try:
            checks, transcript = await citizen_case(persona)
            officer_checks = None

            if persona.get("officer_followup"):
                officer_checks, officer_transcript = await officer_followup(persona)
                transcript.extend(officer_transcript)
                passed = checks["passed"] and officer_checks["passed"]
            else:
                passed = checks["passed"]

            result = {
                "persona_id": persona["id"],
                "persona": persona,
                "started_at": started,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "passed": passed,
                "summary": (
                    "Citizen MCP flow and database postconditions passed."
                    if passed
                    else "One or more citizen/officer database postconditions failed."
                ),
                "checks": {
                    "citizen": checks,
                    "officer": officer_checks,
                },
                "transcript": json.dumps(transcript, ensure_ascii=False, indent=2, default=str),
            }
        except Exception as exc:
            result = {
                "persona_id": persona["id"],
                "persona": persona,
                "started_at": started,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "passed": False,
                "summary": "Evaluation execution failed.",
                "checks": {"exception": str(exc)},
                "transcript": "",
            }

        (RESULTS / f"{persona['id']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str)
        )
        summary.append(result)

    passed = sum(1 for r in summary if r["passed"])
    print(json.dumps({
        "cases": len(summary),
        "passed": passed,
        "failed": len(summary) - passed,
        "results_dir": str(RESULTS),
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
