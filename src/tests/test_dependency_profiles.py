from pathlib import Path

from src.utils.dependencies import dependency_capability_report, dependency_summary


def test_dependency_capability_report_tracks_optional_acceleration_packages():
    report = dependency_capability_report()
    packages = {item.package: item for item in report}

    assert "pyarrow" in packages
    assert packages["pyarrow"].tier == "research"
    assert "numba" in packages
    assert packages["numba"].tier == "acceleration"
    assert all(item.capability for item in report)


def test_dependency_summary_groups_capabilities_by_tier():
    summary = dependency_summary()

    assert "research" in summary["by_tier"]
    assert "broker" in summary["by_tier"]
    assert "capabilities" in summary


def test_requirement_profiles_are_layered_and_explicit():
    root = Path("requirements")
    root_requirement = Path("requirements.txt").read_text(encoding="utf-8").strip()

    assert root_requirement.startswith("-r requirements/")
    assert Path(root_requirement.removeprefix("-r ")).exists()
    assert "pandas==3.0.3" in (root / "base.txt").read_text(encoding="utf-8")
    assert "-r base.txt" in (root / "research.txt").read_text(encoding="utf-8")
    assert "optuna" in (root / "research.txt").read_text(encoding="utf-8")
    assert "alpaca-py" in (root / "broker.txt").read_text(encoding="utf-8")
    assert "numba" in (root / "acceleration.txt").read_text(encoding="utf-8")
    assert "polars" in (root / "acceleration.txt").read_text(encoding="utf-8")
