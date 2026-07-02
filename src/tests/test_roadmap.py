from pathlib import Path


def test_roadmap_tracks_mvp_and_production_readiness_work():
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    items = [line for line in roadmap.splitlines() if line[:2].strip(".").isdigit()]

    assert len(items) >= 70
    assert "Current status: MVP/research scaffold complete, not autonomous-production-ready." in roadmap
    assert "Implemented so far: items 1-30." in roadmap
    assert "Production paper-trading readiness starts at item 31." in roadmap
