from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Union

import pandas as pd

from .artifacts import ImmutableArtifactStore, RunManifest


def parquet_available() -> bool:
    return find_spec("pyarrow") is not None


def require_parquet_support() -> None:
    if not parquet_available():
        raise RuntimeError("Parquet support requires the research dependency profile: pip install -r requirements/research.txt")


@dataclass(frozen=True)
class ParquetArtifactStore:
    """Optional columnar artifact writer for large research outputs."""

    root: Union[str, Path] = "runs/artifacts"
    compression: str = "snappy"

    def __post_init__(self) -> None:
        object.__setattr__(self, "_artifact_store", ImmutableArtifactStore(self.root))

    def run_dir(self, manifest: RunManifest) -> Path:
        return self._artifact_store.run_dir(manifest)

    def write_manifest(self, manifest: RunManifest, overwrite: bool = False) -> Path:
        return self._artifact_store.write_manifest(manifest, overwrite=overwrite)

    def write_dataframe(
        self,
        manifest: RunManifest,
        name: str,
        data: pd.DataFrame,
        overwrite: bool = False,
    ) -> Path:
        require_parquet_support()
        path = self._path(manifest, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite immutable artifact: {path}")
        data.to_parquet(path, engine="pyarrow", compression=self.compression)
        return path

    def read_dataframe(self, manifest: RunManifest, name: str) -> pd.DataFrame:
        require_parquet_support()
        return pd.read_parquet(self._path(manifest, name), engine="pyarrow")

    def _path(self, manifest: RunManifest, name: str) -> Path:
        path = self.run_dir(manifest) / name
        if path.suffix != ".parquet":
            path = path.with_suffix(".parquet")
        return path
