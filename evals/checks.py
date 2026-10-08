"""Database assertions for evaluation cases."""
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
    keys = ["applicant_name","mobile","block","status","decided_by"]
    actual = dict(zip(keys, row))
    checks = {}
    for key, value in expected.items():
        checks[key] = actual.get(key) == value
    return {"passed": all(checks.values()), "actual": actual, "checks": checks}
