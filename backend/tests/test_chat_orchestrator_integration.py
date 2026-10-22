"""Phase 5 — chat routing / feature flag."""
from __future__ import annotations

import asyncio

from app.api.routes import _try_conversational_setup_response
from app.schemas.chat import ChatRequest
from app.services.orchestrator.decision_models import OrchestratorResult, RespondDecision
from app.services.orchestrator.orchestrator import should_route_to_orchestrator


def _request(**overrides):
    payload = {
        "messages": [{"role": "user", "content": "ช่วยเตรียมข้อมูล"}],
        "user_id": "00000000-0000-0000-0000-000000000001",
        "data_setup_session_id": "00000000-0000-0000-0000-000000000010",
        "file_attachment_name": "sales.xlsx",
    }
    payload.update(overrides)
    return ChatRequest(**payload)


def test_feature_flag_disabled_does_not_route(monkeypatch):
    monkeypatch.setattr(
        "app.services.orchestrator.orchestrator.settings.ENABLE_CONVERSATIONAL_DATA_SETUP",
        False,
    )
    assert should_route_to_orchestrator(
        chat_request=_request(),
        session={"id": "s", "status": "processing"},
    ) is False


def test_feature_flag_enabled_routes_non_ready(monkeypatch):
    monkeypatch.setattr(
        "app.services.orchestrator.orchestrator.settings.ENABLE_CONVERSATIONAL_DATA_SETUP",
        True,
    )
    assert should_route_to_orchestrator(
        chat_request=_request(),
        session={"id": "s", "status": "processing"},
    ) is True
    assert should_route_to_orchestrator(
        chat_request=_request(),
        session={"id": "s", "status": "ready"},
    ) is False


def test_try_conversational_setup_uses_orchestrator_when_enabled(monkeypatch):
    monkeypatch.setattr(
        "app.services.orchestrator.orchestrator.settings.ENABLE_CONVERSATIONAL_DATA_SETUP",
        True,
    )
    monkeypatch.setattr(
        "app.api.routes._load_data_setup_session_for_chat",
        lambda *_a, **_k: {
            "id": "00000000-0000-0000-0000-000000000010",
            "status": "processing",
            "user_id": "00000000-0000-0000-0000-000000000001",
        },
    )

    async def fake_orch(**_kwargs):
        return OrchestratorResult(
            decision=RespondDecision(message="กำลังเตรียมข้อมูล"),
            assistant_message="กำลังเตรียมข้อมูล",
            model_used="test-model",
            prompt_version="1.0",
        )

    import app.services.orchestrator as orch_pkg

    monkeypatch.setattr(orch_pkg, "orchestrate_workflow_message", fake_orch)

    response = asyncio.run(
        _try_conversational_setup_response(
            _request(),
            "00000000-0000-0000-0000-000000000001",
        )
    )
    assert response is not None
    assert response.message.content == "กำลังเตรียมข้อมูล"
    assert response.routing["path"] == "conversational_data_setup"


def test_ready_session_skips_orchestrator(monkeypatch):
    monkeypatch.setattr(
        "app.services.orchestrator.orchestrator.settings.ENABLE_CONVERSATIONAL_DATA_SETUP",
        True,
    )
    monkeypatch.setattr(
        "app.api.routes._load_data_setup_session_for_chat",
        lambda *_a, **_k: {"id": "s", "status": "ready"},
    )
    response = asyncio.run(
        _try_conversational_setup_response(
            _request(),
            "00000000-0000-0000-0000-000000000001",
        )
    )
    assert response is None
