from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, Union


def duckdb_available() -> bool:
    return find_spec("duckdb") is not None


def require_duckdb_support() -> None:
    if not duckdb_available():
        raise RuntimeError("DuckDB querying requires the research dependency profile: pip install -r requirements/research.txt")


@dataclass(frozen=True)
class ResearchQueryResult:
    columns: tuple[str, ...]
    rows: tuple[Mapping[str, Any], ...]

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_dict(self) -> dict:
        return {
            "columns": list(self.columns),
            "row_count": self.row_count,
            "rows": [dict(row) for row in self.rows],
        }


class DuckDBResearchStore:
    """Optional query layer for local research artifacts."""

    def __init__(self, database: Union[str, Path] = ":memory:"):
        require_duckdb_support()
        import duckdb

        self.database = str(database)
        self.connection = duckdb.connect(self.database)

    def query(self, sql: str, parameters: Sequence[Any] | None = None) -> ResearchQueryResult:
        cursor = self.connection.execute(sql, parameters or [])
        columns = tuple(column[0] for column in cursor.description or ())
        rows = tuple(dict(zip(columns, row)) for row in cursor.fetchall())
        return ResearchQueryResult(columns, rows)

    def query_jsonl(self, path: Union[str, Path], sql: str = "select * from artifacts") -> ResearchQueryResult:
        return self._query_file(path, "read_json_auto", sql)

    def query_parquet(self, path: Union[str, Path], sql: str = "select * from artifacts") -> ResearchQueryResult:
        return self._query_file(path, "read_parquet", sql)

    def register_jsonl(self, view_name: str, path: Union[str, Path]) -> None:
        self.connection.execute(f"create or replace view {_identifier(view_name)} as select * from read_json_auto('{_path(path)}')")

    def register_parquet(self, view_name: str, path: Union[str, Path]) -> None:
        self.connection.execute(f"create or replace view {_identifier(view_name)} as select * from read_parquet('{_path(path)}')")

    def close(self) -> None:
        self.connection.close()

    def _query_file(self, path: Union[str, Path], reader: str, sql: str) -> ResearchQueryResult:
        self.connection.execute(f"create or replace temp view artifacts as select * from {reader}('{_path(path)}')")
        return self.query(sql)


def query_artifact_file(
    path: Union[str, Path],
    file_format: str,
    sql: str = "select * from artifacts",
) -> ResearchQueryResult:
    store = DuckDBResearchStore()
    try:
        if file_format == "jsonl":
            return store.query_jsonl(path, sql)
        if file_format == "parquet":
            return store.query_parquet(path, sql)
        raise ValueError("file_format must be 'jsonl' or 'parquet'.")
    finally:
        store.close()


def query_many_jsonl(paths: Iterable[Union[str, Path]], sql: str = "select * from artifacts") -> ResearchQueryResult:
    store = DuckDBResearchStore()
    try:
        glob = ",".join(f"'{_path(path)}'" for path in paths)
        store.connection.execute(f"create or replace temp view artifacts as select * from read_json_auto([{glob}])")
        return store.query(sql)
    finally:
        store.close()


def _path(path: Union[str, Path]) -> str:
    return str(path).replace("\\", "/").replace("'", "''")


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
