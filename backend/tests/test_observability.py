import asyncio
import inspect
import json
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.errors import incident_response
from app.core.observability import (
    JsonFormatter,
    bind_correlation_id,
    normalize_correlation_id,
    reset_correlation_id,
)
from app.main import RequestObservabilityMiddleware, health_ready


def test_http_middleware_preserves_safe_correlation_id():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/health/live",
        "headers": [(b"x-correlation-id", b"browser:request-123")],
        "query_string": b"",
        "server": ("test", 80),
        "client": ("test", 1234),
        "scheme": "http",
    }
    request = Request(scope)
    middleware = RequestObservabilityMiddleware(lambda *_args, **_kwargs: None)

    async def call_next(_request):
        return JSONResponse({"status": "ok"})

    response = asyncio.run(middleware.dispatch(request, call_next))
    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "browser:request-123"
    assert response.headers["X-Request-ID"] == "browser:request-123"


def test_invalid_correlation_id_is_rejected():
    assert normalize_correlation_id("contains spaces and\nnewlines") is None


def test_json_formatter_includes_bound_context_and_error_code():
    token = bind_correlation_id("request-42")
    try:
        record = logging.LogRecord(
            "test",
            logging.ERROR,
            __file__,
            1,
            "operation_failed",
            (),
            None,
        )
        record.error_code = "source_operation_failed"
        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_correlation_id(token)
    assert payload["correlation_id"] == "request-42"
    assert payload["error_code"] == "source_operation_failed"


def test_incident_response_does_not_expose_internal_exception_text():
    payload = incident_response("internal_error", "incident-9")
    assert payload["incident_id"] == "incident-9"
    assert payload["error_code"] == "internal_error"
    assert "exception" not in payload


def test_readiness_failure_uses_safe_dependency_incident():
    source = inspect.getsource(health_ready)
    assert 'incident_response("dependency_unavailable", incident_id)' in source
    assert "str(exc)" not in source
