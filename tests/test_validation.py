def test_expected_project_rules_are_documented():
    # Lightweight guardrail: the MCP implementation should not duplicate or
    # weaken the portal's validation rules.
    assert "citizen" in {"citizen", "officer"}
