"""Phase 6 — structured orchestration_resolution on ChatRequest."""
from __future__ import annotations

from app.schemas.chat import ChatRequest


def test_chat_request_accepts_orchestration_resolution():
    req = ChatRequest(
        messages=[{"role": "user", "content": "ดำเนินการต่อ"}],
        user_id="00000000-0000-0000-0000-000000000001",
        orchestration_resolution={
            "decision": "approved",
            "context_updates": {"cleaning_profile": "standard"},
        },
    )
    assert req.orchestration_resolution["decision"] == "approved"


def test_chat_request_accepts_optional_visualization_context():
    req = ChatRequest(
        messages=[{"role": "user", "content": "อธิบายกราฟนี้"}],
        user_id="user-1",
        visualization_context={
            "report_id": "report-1",
            "widget_id": "ranking",
            "filters": {"branch": "North"},
        },
    )

    assert req.visualization_context.report_id == "report-1"
    assert req.visualization_context.filters == {"branch": "North"}
