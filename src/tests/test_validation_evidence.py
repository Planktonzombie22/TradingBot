import json
import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.validation import (
    ValidationCheckSpec,
    ValidationEvidence,
    ValidationManifest,
    build_validation_history_index,
    build_validation_run_metadata,
    build_release_decision_report,
    build_readiness_index,
    build_validation_action_plan,
    evaluate_evidence_freshness,
    execute_validation_check,
    execute_validation_profile,
    load_validation_evidence_bundle,
    stable_payload_digest,
    write_validation_evidence_bundle,
)


def _manifest() -> ValidationManifest:
    return ValidationManifest(
        checks=(
            ValidationCheckSpec("unit_tests", "code", "tests", "Unit tests pass.", "pytest", required_for=("release_readiness",)),
            ValidationCheckSpec("paper_soak", "paper", "operations", "Paper soak passes.", "paper-soak", required_for=("release_readiness",)),
            ValidationCheckSpec("deployment", "deployment", "deployment", "Deployment rehearsal passes.", required_for=("release_readiness",)),
        )
    )


def test_validation_evidence_bundle_loads_latest_evidence_from_files(tmp_path):
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    first = ValidationEvidence("unit_tests", "failed", reason="old_failure", captured_at=now - timedelta(hours=1))
    second = ValidationEvidence("unit_tests", "passed", reason="fixed", captured_at=now)
    payload = {"evidence": [first.to_dict(), second.to_dict()]}
    source = tmp_path / "evidence.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    bundle = load_validation_evidence_bundle((tmp_path,))

    assert bundle.passed
    assert bundle.sources == (str(source),)
    assert bundle.latest_by_check_id["unit_tests"].status == "passed"


def test_validation_evidence_bundle_reports_invalid_sources(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")

    bundle = load_validation_evidence_bundle((bad, tmp_path / "missing.json"))

    assert not bundle.passed
    assert len(bundle.invalid_sources) == 2
    assert {item["reason"] for item in bundle.invalid_sources} == {"invalid_evidence_payload", "missing_path"}


def test_evidence_freshness_flags_stale_and_missing_required_checks():
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    evidence = (
        ValidationEvidence("unit_tests", "passed", captured_at=now - timedelta(hours=2)),
        ValidationEvidence("paper_soak", "passed", captured_at=now),
    )

    report = evaluate_evidence_freshness(
        evidence,
        manifest=_manifest(),
        target="release_readiness",
        max_age_hours=1,
        evaluated_at=now,
    )

    assert not report.passed
    assert report.stale_check_ids == ("unit_tests",)
    assert report.missing_check_ids == ("deployment",)


def test_evidence_freshness_uses_newest_evidence_per_check():
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    evidence = (
        ValidationEvidence("unit_tests", "passed", captured_at=now),
        ValidationEvidence("unit_tests", "failed", captured_at=now - timedelta(hours=3)),
        ValidationEvidence("paper_soak", "passed", captured_at=now),
        ValidationEvidence("deployment", "passed", captured_at=now),
    )

    report = evaluate_evidence_freshness(
        evidence,
        manifest=_manifest(),
        target="release_readiness",
        max_age_hours=1,
        evaluated_at=now,
    )

    assert report.passed


def test_validation_action_plan_prioritizes_missing_failed_and_stale_checks():
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    evidence = (
        ValidationEvidence("unit_tests", "passed", captured_at=now - timedelta(hours=2)),
        ValidationEvidence("paper_soak", "failed", reason="warnings", captured_at=now),
    )
    readiness = build_readiness_index(evidence, manifest=_manifest(), target="release_readiness")
    freshness = evaluate_evidence_freshness(evidence, _manifest(), "release_readiness", 1, now)

    plan = build_validation_action_plan(readiness, freshness)
    actions = {action.check_id: action for action in plan.actions}

    assert not plan.passed
    assert actions["unit_tests"].status == "stale"
    assert actions["paper_soak"].status == "failed"
    assert actions["deployment"].status == "missing"
    assert actions["unit_tests"].command == "pytest"


def test_release_decision_report_blocks_until_current_required_evidence_passes():
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    blocked = build_release_decision_report(
        (ValidationEvidence("unit_tests", "passed", captured_at=now),),
        manifest=_manifest(),
        target="release_readiness",
        evaluated_at=now,
    )
    clean = build_release_decision_report(
        (
            ValidationEvidence("unit_tests", "passed", captured_at=now),
            ValidationEvidence("paper_soak", "passed", captured_at=now),
            ValidationEvidence("deployment", "passed", captured_at=now),
        ),
        manifest=_manifest(),
        target="release_readiness",
        evaluated_at=now,
    )

    assert blocked.decision == "blocked"
    assert not blocked.passed
    assert clean.decision == "release_ready"
    assert clean.passed


def test_execute_validation_check_turns_commands_into_normalized_evidence():
    check = ValidationCheckSpec(
        "unit_tests",
        "code",
        "tests",
        "Unit tests pass.",
        command="pytest",
        expected_artifacts=("reports/tests.json",),
    )

    evidence = execute_validation_check(
        check,
        command_runner=lambda command, timeout: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
        artifact_exists=lambda path: path == "reports/tests.json",
    )

    assert evidence.status == "passed"
    assert evidence.reason == "passed"
    assert evidence.metadata["command_result"]["command"] == "pytest"


def test_execute_validation_check_flags_failed_timeout_and_missing_artifacts():
    failed = execute_validation_check(
        ValidationCheckSpec("failed", "code", "tests", "Failing command.", command="pytest"),
        command_runner=lambda command, timeout: SimpleNamespace(returncode=1, stdout="", stderr="boom"),
    )

    def timeout_runner(command, timeout):
        raise subprocess.TimeoutExpired(command, timeout)

    timed_out = execute_validation_check(
        ValidationCheckSpec("timeout", "runtime", "tests", "Timeout.", command="slow", timeout_seconds=1),
        command_runner=timeout_runner,
    )
    missing_artifact = execute_validation_check(
        ValidationCheckSpec(
            "artifact",
            "storage",
            "tests",
            "Missing artifact.",
            command="make-artifact",
            expected_artifacts=("reports/missing.json",),
        ),
        command_runner=lambda command, timeout: SimpleNamespace(returncode=0, stdout="", stderr=""),
        artifact_exists=lambda path: False,
    )

    assert failed.reason == "command_failed"
    assert timed_out.reason == "command_timeout"
    assert missing_artifact.reason == "missing_expected_artifacts"


def test_validation_run_metadata_tracks_environment_config_and_artifact_digests(tmp_path):
    artifact = tmp_path / "artifact.json"
    artifact.write_text('{"passed": true}', encoding="utf-8")
    older = build_validation_run_metadata(
        "run-old",
        config={"profile": "fast"},
        code_version="abc123",
        provider="sample",
        broker_mode="dry-run",
        created_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )
    newer = build_validation_run_metadata(
        "run-new",
        config={"profile": "full"},
        artifact_paths=(artifact,),
        code_version="def456",
        dependency_versions={"pandas": "2.x"},
        environment={"python": "3.11"},
        created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )

    history = build_validation_history_index((newer, older))
    payload = history.to_dict()

    assert stable_payload_digest({"profile": "full"}) == newer.config_hash
    assert history.latest_run == newer
    assert payload["latest_run_id"] == "run-new"
    assert str(artifact) in newer.artifact_digests


def test_execute_validation_profile_and_write_evidence_bundle(tmp_path):
    manifest = _manifest()
    profile = type(
        "ProfileLike",
        (),
        {
            "select_checks": lambda self, selected_manifest: (
                selected_manifest.by_id()["unit_tests"],
                selected_manifest.by_id()["paper_soak"],
            )
        },
    )()
    metadata = build_validation_run_metadata("run-1", config={"profile": "fast"})

    evidence = execute_validation_profile(
        profile,
        manifest,
        command_runner=lambda command, timeout: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    )
    output = write_validation_evidence_bundle(tmp_path / "bundle.json", evidence, metadata)
    loaded = load_validation_evidence_bundle((output,))

    assert len(evidence) == 2
    assert all(item.status == "passed" for item in evidence)
    assert output.exists()
    assert loaded.passed
    assert {item.check_id for item in loaded.evidence} == {"unit_tests", "paper_soak"}
