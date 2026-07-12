import json

import pandas as pd
import pytest

from src.data import HistoricalDataCache
from src.storage import (
    ImmutableArtifactStore,
    JsonlStore,
    ParquetArtifactStore,
    RunManifest,
    duckdb_available,
    parquet_available,
    query_artifact_file,
)


def test_jsonl_store_writes_records(tmp_path):
    store = JsonlStore(tmp_path)

    path = store.write_many("events", [{"type": "STARTED"}, {"type": "STOPPED"}])

    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["type"] for line in lines] == ["STARTED", "STOPPED"]


def test_immutable_artifact_store_writes_manifest_and_refuses_overwrite(tmp_path):
    manifest = RunManifest.create(
        run_type="backtest",
        strategy="buyHold",
        symbols=["SPY"],
        config={"interval": "1d"},
        data_source={"provider": "sample"},
    )
    store = ImmutableArtifactStore(tmp_path)

    manifest_path = store.write_manifest(manifest)
    payload_path = store.write_json(manifest, "metrics.json", {"total_return": 0.1})
    jsonl_path = store.write_jsonl(manifest, "fills.jsonl", [{"symbol": "SPY"}])

    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["stable_hash"] == manifest.stable_hash
    assert manifest_payload["strategy"] == "buyHold"
    assert payload_path.exists()
    assert jsonl_path.exists()
    with pytest.raises(FileExistsError):
        store.write_json(manifest, "metrics.json", {"total_return": 0.2})


def test_parquet_artifact_store_round_trips_when_available_and_fails_clearly_otherwise(tmp_path):
    manifest = RunManifest.create(
        run_type="research",
        strategy="buyHold",
        symbols=["SPY"],
        config={},
        data_source={"provider": "sample"},
    )
    store = ParquetArtifactStore(tmp_path)
    frame = pd.DataFrame({"Close": [100.0, 101.0]}, index=pd.date_range("2024-01-01", periods=2))

    if not parquet_available():
        with pytest.raises(RuntimeError, match="requirements/research.txt"):
            store.write_dataframe(manifest, "bars", frame)
        return

    path = store.write_dataframe(manifest, "bars", frame)
    restored = store.read_dataframe(manifest, "bars")

    assert path.suffix == ".parquet"
    assert list(restored["Close"]) == [100.0, 101.0]


def test_historical_data_cache_supports_csv_and_optional_parquet_paths(tmp_path):
    frame = pd.DataFrame({"Close": [100.0]}, index=pd.date_range("2024-01-01", periods=1))
    csv_cache = HistoricalDataCache(tmp_path / "csv")
    parquet_cache = HistoricalDataCache(tmp_path / "parquet", storage_format="parquet")

    csv_path = csv_cache.write("sample", "SPY", "1d", frame)

    assert csv_path.suffix == ".csv"
    assert csv_cache.read("sample", "SPY", "1d") is not None
    assert parquet_cache.path_for("sample", "SPY", "1d").suffix == ".parquet"

    if parquet_available():
        parquet_path = parquet_cache.write("sample", "SPY", "1d", frame)
        assert parquet_path.suffix == ".parquet"
        assert list(parquet_cache.read("sample", "SPY", "1d")["Close"]) == [100.0]
    else:
        with pytest.raises(RuntimeError, match="requirements/research.txt"):
            parquet_cache.write("sample", "SPY", "1d", frame)


def test_duckdb_research_query_reads_jsonl_when_available_and_fails_clearly_otherwise(tmp_path):
    path = JsonlStore(tmp_path).write_many(
        "bulk-results",
        [
            {"strategy": "buyHold", "symbol": "SPY", "total_return": 0.10},
            {"strategy": "meanReversion", "symbol": "SPY", "total_return": 0.14},
        ],
    )

    if not duckdb_available():
        with pytest.raises(RuntimeError, match="requirements/research.txt"):
            query_artifact_file(path, "jsonl")
        return

    result = query_artifact_file(
        path,
        "jsonl",
        "select strategy, total_return from artifacts where total_return > 0.11 order by total_return desc",
    )

    assert result.row_count == 1
    assert result.rows[0]["strategy"] == "meanReversion"
