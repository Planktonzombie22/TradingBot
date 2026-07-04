import hashlib
import json
import platform
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Union
from uuid import uuid4


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    run_type: str
    strategy: str
    symbols: list[str]
    config: Dict[str, Any]
    data_source: Dict[str, Any]
    dependency_versions: Dict[str, str] = field(default_factory=dict)
    code_version: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(
        cls,
        run_type: str,
        strategy: str,
        symbols: Iterable[str],
        config: Mapping[str, Any],
        data_source: Mapping[str, Any],
    ) -> "RunManifest":
        return cls(
            run_id=str(uuid4()),
            run_type=run_type,
            strategy=strategy,
            symbols=list(symbols),
            config=dict(config),
            data_source=dict(data_source),
            dependency_versions=_dependency_versions(),
            code_version=_git_revision(),
        )

    @property
    def stable_hash(self) -> str:
        payload = json.dumps(
            {
                "run_type": self.run_type,
                "strategy": self.strategy,
                "symbols": self.symbols,
                "config": self.config,
                "data_source": self.data_source,
                "code_version": self.code_version,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["stable_hash"] = self.stable_hash
        return payload


class ImmutableArtifactStore:
    """Run artifact writer that avoids accidental overwrite of research outputs."""

    def __init__(self, root: Union[str, Path] = "runs/artifacts"):
        self.root = Path(root)

    def run_dir(self, manifest: RunManifest) -> Path:
        return self.root / f"{manifest.created_at:%Y%m%dT%H%M%SZ}-{manifest.run_type}-{manifest.stable_hash}"

    def write_manifest(self, manifest: RunManifest, overwrite: bool = False) -> Path:
        directory = self.run_dir(manifest)
        directory.mkdir(parents=True, exist_ok=True)
        return self.write_json(manifest, "manifest.json", manifest.to_dict(), overwrite=overwrite)

    def write_json(self, manifest: RunManifest, name: str, payload: Mapping[str, Any], overwrite: bool = False) -> Path:
        path = self.run_dir(manifest) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite immutable artifact: {path}")
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return path

    def write_jsonl(self, manifest: RunManifest, name: str, records: Iterable[Mapping[str, Any]], overwrite: bool = False) -> Path:
        path = self.run_dir(manifest) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite immutable artifact: {path}")
        with path.open("w", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(record, default=str) + "\n")
        return path


def _git_revision() -> Optional[str]:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    return completed.stdout.strip() or None


def _dependency_versions() -> Dict[str, str]:
    return {
        "python": platform.python_version(),
    }
