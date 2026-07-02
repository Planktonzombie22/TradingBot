import json

from src.storage import JsonlStore


def test_jsonl_store_writes_records(tmp_path):
    store = JsonlStore(tmp_path)

    path = store.write_many("events", [{"type": "STARTED"}, {"type": "STOPPED"}])

    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["type"] for line in lines] == ["STARTED", "STOPPED"]
