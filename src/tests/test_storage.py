import json

import pytest

from src.storage import ImmutableArtifactStore, JsonlStore, RunManifest


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
