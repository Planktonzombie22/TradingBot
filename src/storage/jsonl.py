import json
from pathlib import Path
from typing import Any, Iterable, Union


class JsonlStore:
    """Append-only JSONL persistence for events and run artifacts."""

    def __init__(self, root: Union[str, Path] = "runs"):
        self.root = Path(root)

    def append(self, name: str, record: dict[str, Any]) -> Path:
        path = self.root / f"{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, default=str) + "\n")
        return path

    def write_many(self, name: str, records: Iterable[dict[str, Any]]) -> Path:
        path = self.root / f"{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(record, default=str) + "\n")
        return path
