from app.services.json_paths import discover_record_paths, resolve_record_path
from app.services.large_data_ingest import ingest_json_bytes


NESTED = {
    "meta": {"page": 1},
    "payload": {"items": [{"date": "2026-01-01", "sales": 10}, {"date": "2026-01-02", "sales": 20}]},
}


def test_discovers_and_resolves_nested_record_array():
    assert "payload.items[]" in discover_record_paths(NESTED)
    assert resolve_record_path(NESTED, "payload.items[]") == NESTED["payload"]["items"]


def test_json_ingest_uses_requested_record_path():
    import json

    handle = ingest_json_bytes(json.dumps(NESTED).encode(), json_path="payload.items[]")
    assert handle is not None
    assert handle.column_names() == ["date", "sales"]
    assert handle.row_count() == 2
