import ast
from pathlib import Path

def test_citizen_server_has_no_officer_decision_tool():
    source = Path("mcp/citizen_server.py").read_text()
    assert "decide_application" not in source
    assert "approve" not in source.lower()

def test_officer_server_has_decision_tool():
    source = Path("mcp/officer_server.py").read_text()
    assert "decide_application" in source
