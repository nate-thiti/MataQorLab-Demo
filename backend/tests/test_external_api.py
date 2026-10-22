"""Tests for REST API connection HTTP helpers."""
from unittest.mock import MagicMock, patch

from app.services.external_api import (
    build_request_headers,
    fetch_external_api,
    normalize_header_items,
    parse_request_body,
)


def test_normalize_header_items_skips_empty_keys():
    items = [{"key": " x-api-key ", "value": "abc"}, {"key": "", "value": "x"}, {"key": "x-secret-key", "value": None}]
    assert normalize_header_items(items) == [
        {"key": "x-api-key", "value": "abc"},
        {"key": "x-secret-key", "value": ""},
    ]


def test_build_request_headers_prefers_request_headers_json():
    conn = {
        "request_headers": [{"key": "x-api-key", "value": "k1"}],
        "auth_header_name": "Authorization",
        "auth_header_value": "legacy",
    }
    assert build_request_headers(conn) == {"x-api-key": "k1"}


def test_build_request_headers_legacy_fallback():
    conn = {"auth_header_name": "Authorization", "auth_header_value": "Bearer tok"}
    assert build_request_headers(conn) == {"Authorization": "Bearer tok"}


def test_parse_request_body_accepts_dict_and_json_string():
    assert parse_request_body('{"companyCode": "DELICIOUS"}') == {"companyCode": "DELICIOUS"}
    assert parse_request_body({}) is None


@patch("app.services.external_api.validate_outbound_url", side_effect=lambda value: value)
@patch("app.services.external_api.requests.post")
def test_fetch_external_api_post_adds_json_content_type(mock_post, _mock_validate):
    mock_post.return_value = MagicMock(status_code=200)
    body = {"companyCode": "TESTER01", "soDocNo": "SO-1"}
    fetch_external_api(
        method="POST",
        url="https://example.com/api",
        headers={"x-api-key": "k", "x-secret-key": "s"},
        body=body,
    )
    mock_post.assert_called_once()
    kwargs = mock_post.call_args.kwargs
    assert kwargs["json"] == body
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["headers"]["x-api-key"] == "k"
    assert kwargs["allow_redirects"] is False


@patch("app.services.external_api.validate_outbound_url", side_effect=lambda value: value)
@patch("app.services.external_api.requests.get")
def test_fetch_external_api_get_no_body(mock_get, _mock_validate):
    mock_get.return_value = MagicMock(status_code=200)
    fetch_external_api(method="GET", url="https://example.com/data", headers={"Authorization": "Bearer x"})
    mock_get.assert_called_once()
    assert mock_get.call_args.kwargs["headers"] == {"Authorization": "Bearer x"}
    assert mock_get.call_args.kwargs["allow_redirects"] is False
