from html import escape
from pathlib import Path
from typing import Any, Mapping, Sequence


def render_readiness_html(bundle: Mapping[str, Any]) -> str:
    readiness = dict(bundle.get("readiness_index", {}))
    action_plan = dict(bundle.get("action_plan") or bundle.get("release_decision", {}).get("action_plan", {}))
    freshness = dict(bundle.get("evidence_freshness") or bundle.get("release_decision", {}).get("freshness_report", {}))
    not_live_ready = dict(bundle.get("not_live_ready", {}))
    release_decision = dict(bundle.get("release_decision", {}))
    actions = list(action_plan.get("actions", ()))
    checks = list(readiness.get("checks", ()))
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>TradingBot Readiness</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #17202a; background: #f7f9fb; }}
    main {{ max-width: 1120px; margin: 0 auto; }}
    section {{ background: white; border: 1px solid #d8dee8; border-radius: 6px; padding: 16px; margin-bottom: 16px; }}
    h1, h2 {{ margin: 0 0 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .metric {{ border: 1px solid #e2e7ef; border-radius: 4px; padding: 12px; background: #fbfcfe; }}
    .label {{ color: #5d6d7e; font-size: 12px; text-transform: uppercase; }}
    .value {{ font-size: 22px; font-weight: 700; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #e6ebf2; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f2f5f9; }}
    .pass {{ color: #127a36; font-weight: 700; }}
    .fail {{ color: #a12828; font-weight: 700; }}
    code {{ font-family: Consolas, monospace; font-size: 12px; }}
  </style>
</head>
<body>
<main>
  <h1>TradingBot Readiness</h1>
  <section>
    <div class="grid">
      {_metric("Target", readiness.get("target", "unknown"))}
      {_metric("Readiness", f"{float(readiness.get('readiness_score', 0.0)):.1%}")}
      {_metric("Release Decision", release_decision.get("decision", "n/a"))}
      {_metric("Live Status", not_live_ready.get("status", "n/a"))}
      {_metric("Missing", len(readiness.get("missing_required", ())))}
      {_metric("Failed", len(readiness.get("failed_required", ())))}
      {_metric("Stale", len(freshness.get("stale_check_ids", ())))}
    </div>
  </section>
  <section>
    <h2>Next Actions</h2>
    {_actions_table(actions)}
  </section>
  <section>
    <h2>Required Checks</h2>
    {_checks_table(checks)}
  </section>
  <section>
    <h2>Freshness</h2>
    <p>Evaluated at: <code>{escape(str(freshness.get("evaluated_at", "n/a")))}</code></p>
    <p>Max age hours: <code>{escape(str(freshness.get("max_age_hours", "n/a")))}</code></p>
  </section>
</main>
</body>
</html>"""
    return html


def write_readiness_html_page(bundle: Mapping[str, Any], path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_readiness_html(bundle), encoding="utf-8")
    return destination


def _metric(label: str, value: Any) -> str:
    return f'<div class="metric"><div class="label">{escape(label)}</div><div class="value">{escape(str(value))}</div></div>'


def _actions_table(actions: Sequence[Mapping[str, Any]]) -> str:
    if not actions:
        return '<p class="pass">No blocking actions.</p>'
    rows = []
    for action in actions:
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(action.get('check_id', '')))}</code></td>"
            f"<td>{escape(str(action.get('status', '')))}</td>"
            f"<td>{escape(str(action.get('reason', '')))}</td>"
            f"<td>{escape(str(action.get('subsystem', '')))}</td>"
            f"<td><code>{escape(str(action.get('command') or ''))}</code></td>"
            "</tr>"
        )
    return "<table><thead><tr><th>Check</th><th>Status</th><th>Reason</th><th>Subsystem</th><th>Command</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _checks_table(checks: Sequence[Mapping[str, Any]]) -> str:
    if not checks:
        return "<p>No checks in this bundle.</p>"
    rows = []
    for item in checks:
        spec = dict(item.get("spec", {}))
        evidence = dict(item.get("evidence", {}))
        status = evidence.get("status", "missing")
        css = "pass" if status == "passed" else "fail"
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(spec.get('check_id', '')))}</code></td>"
            f'<td class="{css}">{escape(str(status))}</td>'
            f"<td>{escape(str(spec.get('category', '')))}</td>"
            f"<td>{escape(str(evidence.get('reason', '')))}</td>"
            "</tr>"
        )
    return "<table><thead><tr><th>Check</th><th>Status</th><th>Category</th><th>Reason</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
