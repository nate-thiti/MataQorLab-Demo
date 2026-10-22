"""Tests for API pagination helpers."""
from unittest.mock import MagicMock, patch

from app.services.api_pagination import (
    extract_records,
    get_nested,
    get_pagination_config,
    iter_api_records,
    stream_api_records_to_ndjson,
)


def test_get_pagination_config_from_request_body():
    conn = {"request_body": {"filter": "x", "_pagination": {"style": "offset", "page_size": 50}}}
    assert get_pagination_config(conn) == {"style": "offset", "page_size": 50}


def test_extract_records_with_path():
    data = {"result": {"items": [{"id": 1}, {"id": 2}]}}
    assert len(extract_records(data, "result.items")) == 2


def test_get_nested_dot_path():
    assert get_nested({"a": {"b": [1]}}, "a.b") == [1]


@patch("app.services.api_pagination.fetch_external_api")
def test_iter_api_records_offset_pagination(mock_fetch):
    pages = [
        {"data": [{"id": 1}, {"id": 2}]},
        {"data": [{"id": 3}]},
    ]
    mock_fetch.side_effect = [
        MagicMock(status_code=200, raise_for_status=lambda: None, json=lambda d=p: d)
        for p in pages
    ]
    conn = {
        "method": "GET",
        "url": "https://example.com/items",
        "request_body": {
            "_pagination": {
                "style": "offset",
                "page_size": 2,
                "max_pages": 5,
                "records_path": "data",
                "offset_param": "offset",
                "limit_param": "limit",
            }
        },
    }
    records = list(iter_api_records(conn, timeout=5))
    assert [r["id"] for r in records] == [1, 2, 3]
    assert mock_fetch.call_count == 2


@patch("app.services.api_pagination.fetch_external_api")
def test_stream_api_records_to_ndjson(mock_fetch):
    mock_fetch.return_value = MagicMock(
        status_code=200,
        raise_for_status=lambda: None,
        json=lambda: {"rows": [{"x": "a"}]},
    )
    conn = {
        "method": "GET",
        "url": "https://example.com/data",
        "request_body": {"_pagination": {"records_path": "rows", "page_size": 100}},
    }
    import tempfile
    import os

    path = tempfile.mktemp(suffix=".ndjson")
    try:
        count = stream_api_records_to_ndjson(conn, path, timeout=5)
        assert count == 1
        with open(path, encoding="utf-8") as handle:
            assert '"x": "a"' in handle.read()
    finally:
        if os.path.exists(path):
            os.unlink(path)
