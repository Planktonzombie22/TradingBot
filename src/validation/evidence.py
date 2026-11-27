import json
import hashlib
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .manifest import ValidationEvidence, ValidationManifest, ValidationProfile, ValidationReadinessIndex, build_not_live_ready_report, build_readiness_index, default_validation_manifest


@dataclass(frozen=True)
class ValidationEvidenceBundle:
    evidence: tuple[ValidationEvidence, ...]
    sources: tuple[str, ...] = ()
    invalid_sources: tuple[Mapping[str, Any], ...] = ()

    @property
    def passed(self) -> bool:
        return not self.invalid_sources

    @property
    def latest_by_check_id(self) -> dict[str, ValidationEvidence]:
        latest: dict[str, ValidationEvidence] = {}
        for item in self.evidence:
            previous = latest.get(item.check_id)
            if previous is None or item.captured_at > previous.captured_at:
                latest[item.check_id] = item
        return latest

    def latest_evidence(self) -> tuple[ValidationEvidence, ...]:
        return tuple(self.latest_by_check_id.values())

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "sources": list(self.sources),
            "invalid_sources": [dict(item) for item in self.invalid_sources],
            "evidence": [item.to_dict() for item in self.evidence],
            "latest_evidence": [item.to_dict() for item in self.latest_evidence()],
        }


@dataclass(frozen=True)
class EvidenceFreshnessReport:
    stale_check_ids: tuple[str, ...]
    missing_check_ids: tuple[str, ...]
    max_age_hours: float
    evaluated_at: datetime

    @property
    def passed(self) -> bool:
        return not self.stale_check_ids and not self.missing_check_ids

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "stale_check_ids": list(self.stale_check_ids),
            "missing_check_ids": list(self.missing_check_ids),
            "max_age_hours": self.max_age_hours,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


@dataclass(frozen=True)
class ValidationAction:
    check_id: str
    category: str
    subsystem: str
    status: str
    reason: str
    command: str | None = None

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "category": self.category,
            "subsystem": self.subsystem,
            "status": self.status,
            "reason": self.reason,
            "command": self.command,
        }


@dataclass(frozen=True)
class ValidationActionPlan:
    target: str
    actions: tuple[ValidationAction, ...]

    @property
    def passed(self) -> bool:
        return not self.actions

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "passed": self.passed,
            "actions": [action.to_dict() for action in self.actions],
            "next_commands": [action.command for action in self.actions if action.command],
        }


@dataclass(frozen=True)
class ReleaseDecisionReport:
    readiness_index: ValidationReadinessIndex
    freshness_report: EvidenceFreshnessReport
    action_plan: ValidationActionPlan
    not_live_ready: Mapping[str, Any]

    @property
    def passed(self) -> bool:
        return self.readiness_index.passed and self.freshness_report.passed and self.action_plan.passed

    @property
    def decision(self) -> str:
        return "release_ready" if self.passed else "blocked"

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "passed": self.passed,
            "readiness_index": self.readiness_index.to_dict(),
            "freshness_report": self.freshness_report.to_dict(),
            "action_plan": self.action_plan.to_dict(),
            "not_live_ready": dict(self.not_live_ready),
        }


@dataclass(frozen=True)
class ValidationCommandResult:
    command: str
    exit_code: int
    elapsed_seconds: float
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    expected_artifacts_present: bool = True
    missing_artifacts: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and self.expected_artifacts_present

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "elapsed_seconds": self.elapsed_seconds,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "expected_artifacts_present": self.expected_artifacts_present,
            "missing_artifacts": list(self.missing_artifacts),
        }


@dataclass(frozen=True)
class ValidationRunMetadata:
    run_id: str
    code_version: str = "unknown"
    config_hash: str = ""
    environment: Mapping[str, Any] = None
    dependency_versions: Mapping[str, str] = None
    provider: str = ""
    broker_mode: str = ""
    artifact_digests: Mapping[str, str] = None
    created_at: datetime = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now(timezone.utc))
        if self.environment is None:
            object.__setattr__(self, "environment", {})
        if self.dependency_versions is None:
            object.__setattr__(self, "dependency_versions", {})
        if self.artifact_digests is None:
            object.__setattr__(self, "artifact_digests", {})

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "code_version": self.code_version,
            "config_hash": self.config_hash,
            "environment": dict(self.environment),
            "dependency_versions": dict(self.dependency_versions),
            "provider": self.provider,
            "broker_mode": self.broker_mode,
            "artifact_digests": dict(self.artifact_digests),
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class ValidationEvidenceHistory:
    runs: tuple[ValidationRunMetadata, ...]

    @property
    def latest_run(self) -> ValidationRunMetadata | None:
        if not self.runs:
            return None
        return max(self.runs, key=lambda run: run.created_at)

    def by_run_id(self) -> dict[str, ValidationRunMetadata]:
        return {run.run_id: run for run in self.runs}

    def to_dict(self) -> dict:
        return {
            "runs": [run.to_dict() for run in self.runs],
            "latest_run_id": self.latest_run.run_id if self.latest_run else None,
        }


def load_validation_evidence_bundle(paths: Sequence[str | Path]) -> ValidationEvidenceBundle:
    evidence: list[ValidationEvidence] = []
    sources: list[str] = []
    invalid_sources: list[Mapping[str, Any]] = []
    for raw_path in paths:
        path = Path(raw_path)
        candidates = sorted(path.glob("*.json")) if path.is_dir() else [path]
        for candidate in candidates:
            if not candidate.exists():
                invalid_sources.append({"path": str(candidate), "reason": "missing_path"})
                continue
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
                parsed = _parse_evidence_payload(payload)
            except Exception as exc:  # noqa: BLE001 - evidence loading should report bad sources, not crash release summaries.
                invalid_sources.append({"path": str(candidate), "reason": "invalid_evidence_payload", "error": str(exc)})
                continue
            sources.append(str(candidate))
            evidence.extend(parsed)
    return ValidationEvidenceBundle(tuple(evidence), tuple(sources), tuple(invalid_sources))


def build_validation_run_metadata(
    run_id: str,
    config: Mapping[str, Any] | None = None,
    artifact_paths: Sequence[str | Path] = (),
    code_version: str = "unknown",
    provider: str = "",
    broker_mode: str = "",
    dependency_versions: Mapping[str, str] | None = None,
    environment: Mapping[str, Any] | None = None,
    created_at: datetime | None = None,
) -> ValidationRunMetadata:
    config_payload = dict(config or {})
    return ValidationRunMetadata(
        run_id=run_id,
        code_version=code_version,
        config_hash=stable_payload_digest(config_payload) if config_payload else "",
        environment=dict(environment or default_environment_metadata()),
        dependency_versions=dict(dependency_versions or {}),
        provider=provider,
        broker_mode=broker_mode,
        artifact_digests=digest_artifacts(artifact_paths),
        created_at=created_at or datetime.now(timezone.utc),
    )


def build_validation_history_index(runs: Sequence[ValidationRunMetadata]) -> ValidationEvidenceHistory:
    return ValidationEvidenceHistory(tuple(sorted(runs, key=lambda run: run.created_at)))


def stable_payload_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def digest_artifacts(paths: Sequence[str | Path]) -> dict[str, str]:
    digests = {}
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        digests[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def default_environment_metadata() -> dict:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


def execute_validation_check(
    check,
    command_runner=None,
    artifact_exists=None,
) -> ValidationEvidence:
    if not check.command:
        return ValidationEvidence(check.check_id, "skipped", reason="no_command")
    result = _run_validation_command(check.command, check.timeout_seconds, command_runner)
    artifact_exists = artifact_exists or (lambda path: Path(path).exists())
    missing_artifacts = tuple(path for path in check.expected_artifacts if not artifact_exists(path))
    if missing_artifacts:
        result = ValidationCommandResult(
            command=result.command,
            exit_code=result.exit_code,
            elapsed_seconds=result.elapsed_seconds,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
            expected_artifacts_present=False,
            missing_artifacts=missing_artifacts,
        )
    if result.passed:
        status = "passed"
        reason = "passed"
    elif result.timed_out:
        status = "failed"
        reason = "command_timeout"
    elif missing_artifacts:
        status = "failed"
        reason = "missing_expected_artifacts"
    else:
        status = "failed"
        reason = "command_failed"
    return ValidationEvidence(
        check.check_id,
        status,
        elapsed_seconds=result.elapsed_seconds,
        reason=reason,
        metadata={"command_result": result.to_dict()},
    )


def execute_validation_checks(
    checks: Sequence[Any],
    command_runner=None,
    artifact_exists=None,
) -> tuple[ValidationEvidence, ...]:
    return tuple(
        execute_validation_check(check, command_runner=command_runner, artifact_exists=artifact_exists)
        for check in checks
    )


def execute_validation_profile(
    profile: ValidationProfile,
    manifest: ValidationManifest | None = None,
    command_runner=None,
    artifact_exists=None,
) -> tuple[ValidationEvidence, ...]:
    manifest = manifest or default_validation_manifest()
    return execute_validation_checks(
        profile.select_checks(manifest),
        command_runner=command_runner,
        artifact_exists=artifact_exists,
    )


def write_validation_evidence_bundle(
    path: str | Path,
    evidence: Sequence[ValidationEvidence],
    run_metadata: ValidationRunMetadata | None = None,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_metadata": run_metadata.to_dict() if run_metadata else None,
        "evidence": [item.to_dict() for item in evidence],
    }
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return destination


def evaluate_evidence_freshness(
    evidence: Sequence[ValidationEvidence],
    manifest: ValidationManifest | None = None,
    target: str = "paper_readiness",
    max_age_hours: float = 24.0,
    evaluated_at: datetime | None = None,
) -> EvidenceFreshnessReport:
    manifest = manifest or default_validation_manifest()
    evaluated_at = evaluated_at or datetime.now(timezone.utc)
    latest: dict[str, ValidationEvidence] = {}
    for item in evidence:
        previous = latest.get(item.check_id)
        if previous is None or item.captured_at > previous.captured_at:
            latest[item.check_id] = item
    required = manifest.required_checks(target)
    threshold = timedelta(hours=max_age_hours)
    missing = []
    stale = []
    for check in required:
        item = latest.get(check.check_id)
        if item is None:
            missing.append(check.check_id)
            continue
        captured_at = _aware_utc(item.captured_at)
        if evaluated_at - captured_at > threshold:
            stale.append(check.check_id)
    return EvidenceFreshnessReport(tuple(stale), tuple(missing), max_age_hours, evaluated_at)


def build_validation_action_plan(
    readiness_index: ValidationReadinessIndex,
    freshness_report: EvidenceFreshnessReport | None = None,
) -> ValidationActionPlan:
    evidence_by_id = readiness_index.evidence_by_id
    stale = set(freshness_report.stale_check_ids if freshness_report else ())
    actions: list[ValidationAction] = []
    for check in readiness_index.required_checks:
        evidence = evidence_by_id.get(check.check_id)
        status = evidence.status if evidence else "missing"
        reason = evidence.reason if evidence else "no_current_evidence"
        if check.check_id in stale:
            status = "stale"
            reason = "evidence_stale"
        if status == "passed":
            continue
        actions.append(
            ValidationAction(
                check.check_id,
                check.category,
                check.subsystem,
                status,
                reason,
                check.command,
            )
        )
    return ValidationActionPlan(readiness_index.target, tuple(actions))


def build_release_decision_report(
    evidence: Sequence[ValidationEvidence],
    manifest: ValidationManifest | None = None,
    target: str = "release_readiness",
    max_age_hours: float = 24.0,
    evaluated_at: datetime | None = None,
) -> ReleaseDecisionReport:
    manifest = manifest or default_validation_manifest()
    readiness = build_readiness_index(evidence, manifest=manifest, target=target)
    freshness = evaluate_evidence_freshness(evidence, manifest, target, max_age_hours, evaluated_at)
    action_plan = build_validation_action_plan(readiness, freshness)
    not_live_ready = build_not_live_ready_report(readiness).to_dict()
    return ReleaseDecisionReport(readiness, freshness, action_plan, not_live_ready)


def _parse_evidence_payload(payload: Any) -> tuple[ValidationEvidence, ...]:
    if isinstance(payload, list):
        return tuple(_parse_evidence_item(item) for item in payload)
    if not isinstance(payload, Mapping):
        raise ValueError("Evidence payload must be an object or list.")
    if "check_id" in payload and "status" in payload:
        return (_parse_evidence_item(payload),)
    if isinstance(payload.get("evidence"), list):
        return tuple(_parse_evidence_item(item) for item in payload["evidence"])
    readiness = payload.get("readiness_index")
    if isinstance(readiness, Mapping) and isinstance(readiness.get("checks"), list):
        return tuple(
            _parse_evidence_item(item["evidence"])
            for item in readiness["checks"]
            if isinstance(item, Mapping) and isinstance(item.get("evidence"), Mapping)
        )
    return ()


def _parse_evidence_item(payload: Mapping[str, Any]) -> ValidationEvidence:
    captured_at = payload.get("captured_at")
    return ValidationEvidence(
        check_id=str(payload["check_id"]),
        status=str(payload["status"]),
        artifact_path=payload.get("artifact_path"),
        elapsed_seconds=payload.get("elapsed_seconds"),
        reason=str(payload.get("reason", "")),
        captured_at=datetime.fromisoformat(captured_at) if captured_at else datetime.now(timezone.utc),
        metadata=dict(payload.get("metadata", {})),
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _run_validation_command(command: str, timeout_seconds: float | None, command_runner=None) -> ValidationCommandResult:
    started = time.perf_counter()
    timeout = timeout_seconds if timeout_seconds and timeout_seconds > 0 else None
    try:
        if command_runner is None:
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        else:
            completed = command_runner(command, timeout)
        elapsed = time.perf_counter() - started
        return ValidationCommandResult(
            command=command,
            exit_code=int(getattr(completed, "returncode", 0)),
            elapsed_seconds=elapsed,
            stdout=str(getattr(completed, "stdout", "")),
            stderr=str(getattr(completed, "stderr", "")),
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        return ValidationCommandResult(
            command=command,
            exit_code=124,
            elapsed_seconds=elapsed,
            stdout=str(exc.stdout or ""),
            stderr=str(exc.stderr or ""),
            timed_out=True,
        )
    except Exception as exc:  # noqa: BLE001 - validation command failures should be evidence, not hard crashes.
        elapsed = time.perf_counter() - started
        return ValidationCommandResult(
            command=command,
            exit_code=1,
            elapsed_seconds=elapsed,
            stderr=str(exc),
        )
