import openai
from unittest.mock import MagicMock

from app.core.llm_errors import stream_error_payload


def _api_error(status_code: int, body: dict) -> openai.APIStatusError:
    response = MagicMock()
    response.status_code = status_code
    response.request = MagicMock()
    return openai.APIStatusError("error", response=response, body=body)


def test_stream_error_payload_credits():
    exc = _api_error(402, {"error": {"message": "Insufficient credits. Purchase more.", "code": 402}})
    payload = stream_error_payload(exc)
    assert payload["code"] == "llm_credits"
    assert "Insufficient credits" in payload["detail"]


def test_stream_error_payload_provider_unavailable():
    exc = _api_error(404, {"error": {"message": "No allowed providers are available.", "code": 404}})
    payload = stream_error_payload(exc)
    assert payload["code"] == "provider_unavailable"
