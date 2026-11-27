from src.reporting import render_readiness_html, write_readiness_html_page


def test_readiness_html_renders_summary_actions_and_checks(tmp_path):
    bundle = {
        "readiness_index": {
            "target": "release_readiness",
            "readiness_score": 0.5,
            "missing_required": ["deployment"],
            "failed_required": [],
            "checks": [
                {
                    "spec": {"check_id": "unit_tests", "category": "code"},
                    "evidence": {"status": "passed", "reason": "passed"},
                },
                {
                    "spec": {"check_id": "deployment", "category": "deployment"},
                    "evidence": {"status": "missing", "reason": "no_current_evidence"},
                },
            ],
        },
        "action_plan": {
            "actions": [
                {
                    "check_id": "deployment",
                    "status": "missing",
                    "reason": "no_current_evidence",
                    "subsystem": "deployment",
                    "command": None,
                }
            ]
        },
        "evidence_freshness": {"stale_check_ids": [], "evaluated_at": "2026-07-16T00:00:00Z", "max_age_hours": 24},
        "not_live_ready": {"status": "not_live_ready"},
        "release_decision": {"decision": "blocked"},
    }

    html = render_readiness_html(bundle)
    output = write_readiness_html_page(bundle, tmp_path / "readiness.html")

    assert "TradingBot Readiness" in html
    assert "release_readiness" in html
    assert "deployment" in html
    assert "blocked" in html
    assert output.exists()
    assert output.read_text(encoding="utf-8") == html
