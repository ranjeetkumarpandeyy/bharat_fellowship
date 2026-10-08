import json
from pathlib import Path
from flask import Blueprint, render_template_string

dashboard = Blueprint("eval_dashboard", __name__)

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
PERSONAS = ROOT / "personas.json"

HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Sewa Setu — Agent Evaluation</title>
<style>
body{font-family:system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;background:#f7f7f5;color:#202124}
.card{background:white;border:1px solid #ddd;border-radius:14px;padding:18px;margin:14px 0}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.big{font-size:28px;font-weight:700}.muted{color:#666}
.pass{color:#147d3f;font-weight:700}.fail{color:#b42318;font-weight:700}
pre{white-space:pre-wrap;background:#f4f4f4;padding:12px;border-radius:8px}
</style>
</head>
<body>
<h1>Sewa Setu — Agent Evaluation</h1>
<p class="muted">Database-backed evaluation results for the citizen and officer MCPs.</p>
<div class="grid">
  <div class="card"><div class="big">{{total}}</div><div class="muted">Cases</div></div>
  <div class="card"><div class="big">{{passed}}</div><div class="muted">Passed</div></div>
  <div class="card"><div class="big">{{failed}}</div><div class="muted">Failed</div></div>
  <div class="card"><div class="big">{{rate}}%</div><div class="muted">Pass rate</div></div>
</div>
{% for r in results %}
<div class="card">
<h2>{{r.get('persona_id', 'case')}}</h2>
<p class="{{'pass' if r.get('passed') else 'fail'}}">{{'PASS' if r.get('passed') else 'FAIL'}}</p>
<p>{{r.get('summary','')}}</p>
{% if r.get('checks') %}<pre>{{r.get('checks')|tojson(indent=2)}}</pre>{% endif %}
{% if r.get('transcript') %}<details><summary>Conversation</summary><pre>{{r.get('transcript')}}</pre></details>{% endif %}
</div>
{% endfor %}
</body></html>
"""

@dashboard.get("/eval-dashboard")
def eval_dashboard():
    results = []
    if RESULTS.exists():
        for path in sorted(RESULTS.glob("*.json")):
            try:
                results.append(json.loads(path.read_text()))
            except Exception:
                pass
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    failed = total - passed
    rate = round((passed / total) * 100, 1) if total else 0
    return render_template_string(
        HTML, total=total, passed=passed, failed=failed, rate=rate, results=results
    )
