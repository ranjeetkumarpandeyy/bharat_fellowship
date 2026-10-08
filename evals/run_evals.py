"""
Evaluation runner skeleton.

The brief requires playing personas through a real MCP client and then checking
the portal database. Keep the LLM/client adapter small: the assertions in
checks.py are the acceptance criteria, not a model's self-report.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def load_personas():
    return json.loads((ROOT / "personas.json").read_text())

if __name__ == "__main__":
    for p in load_personas():
        print(f"[EVAL CASE] {p['id']}: {p['goal']}")
    print("Wire your MCP client adapter here, then persist one JSON result per case in evals/results/.")
