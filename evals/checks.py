"""Database assertions used by the Sewa Setu evaluation runner."""
def _fetch(conn, mobile):
    cur = conn.cursor()
    cur.execute(
        """SELECT id, application_no, applicant_name, mobile, block, status, decided_by
           FROM applications WHERE mobile=%s ORDER BY submitted_at DESC LIMIT 1""",
        (mobile,),
    )
    row = cur.fetchone()
    cur.close()
    if not row:
        return None
    keys = ["id", "application_no", "applicant_name", "mobile", "block", "status", "decided_by"]
    return dict(zip(keys, row))


def check_application_by_mobile(conn, mobile, expected):
    actual = _fetch(conn, mobile)
    if not actual:
        return {"passed": False, "actual": None, "checks": {"application_exists": False}}
    checks = {"application_exists": True}
    for key, value in expected.items():
        checks[key] = actual.get(key) == value
    return {"passed": all(checks.values()), "actual": actual, "checks": checks}


def check_no_application_for_mobile(conn, mobile):
    actual = _fetch(conn, mobile)
    passed = actual is None
    return {
        "passed": passed,
        "actual": actual,
        "checks": {"no_application_created": passed},
    }


def check_decision(conn, mobile, expected_status, expected_officer=None):
    actual = _fetch(conn, mobile)
    if not actual:
        return {"passed": False, "actual": None, "checks": {"application_exists": False}}
    checks = {
        "application_exists": True,
        "status": actual.get("status") == expected_status,
    }
    if expected_officer is not None:
        checks["decided_by"] = actual.get("decided_by") == expected_officer
    return {"passed": all(checks.values()), "actual": actual, "checks": checks}


def check_application(conn, application_id, expected):
    cur = conn.cursor()
    cur.execute(
        """SELECT applicant_name, mobile, block, status, decided_by
           FROM applications WHERE id=%s""",
        (application_id,),
    )
    row = cur.fetchone()
    cur.close()
    if not row:
        return {"passed": False, "reason": "application not found"}
    keys = ["applicant_name", "mobile", "block", "status", "decided_by"]
    actual = dict(zip(keys, row))
    checks = {key: actual.get(key) == value for key, value in expected.items()}
    return {"passed": all(checks.values()), "actual": actual, "checks": checks}
