"""E2E-09 / E2E-10 — ready→analysis handoff + feature flag."""
from __future__ import annotations

from app.schemas.chat import ChatRequest
from app.services.orchestrator.orchestrator import should_route_to_orchestrator


def _request(**overrides):
    payload = {
        "messages": [{"role": "user", "content": "ยอดขายรวมเท่าไหร่"}],
        "user_id": "00000000-0000-0000-0000-000000000001",
        "data_setup_session_id": "00000000-0000-0000-0000-000000000010",
        "file_attachment_name": "sales_clean.csv",
    }
    payload.update(overrides)
    return ChatRequest(**payload)


def test_e2e09_ready_session_skips_orchestrator_setup_path(monkeypatch):
    monkeypatch.setattr(
        "app.services.orchestrator.orchestrator.settings.ENABLE_CONVERSATIONAL_DATA_SETUP",
        True,
    )
    assert should_route_to_orchestrator(
        chat_request=_request(),
        session={"id": "s", "status": "ready"},
    ) is False


def test_e2e10_flag_disabled_blocks_conversational_routing(monkeypatch):
    monkeypatch.setattr(
        "app.services.orchestrator.orchestrator.settings.ENABLE_CONVERSATIONAL_DATA_SETUP",
        False,
    )
    assert should_route_to_orchestrator(
        chat_request=_request(),
        session={"id": "s", "status": "processing"},
    ) is False


def test_e2e10_flag_enabled_routes_non_ready(monkeypatch):
    monkeypatch.setattr(
        "app.services.orchestrator.orchestrator.settings.ENABLE_CONVERSATIONAL_DATA_SETUP",
        True,
    )
    assert should_route_to_orchestrator(
        chat_request=_request(),
        session={"id": "s", "status": "processing"},
    ) is True


def test_capabilities_endpoint_exposes_flag(monkeypatch):
    import asyncio

    import httpx

    from app.main import app
    from app.core.config import settings

    async def exercise_endpoint():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            monkeypatch.setattr(settings, "ENABLE_CONVERSATIONAL_DATA_SETUP", True)
            response = await client.get("/api/v1/capabilities")
            assert response.status_code == 200
            assert response.json()["conversational_data_setup"] is True

            monkeypatch.setattr(settings, "ENABLE_CONVERSATIONAL_DATA_SETUP", False)
            response = await client.get("/api/v1/capabilities")
            assert response.json()["conversational_data_setup"] is False

    asyncio.run(exercise_endpoint())
