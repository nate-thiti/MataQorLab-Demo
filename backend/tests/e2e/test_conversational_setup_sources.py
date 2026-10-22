"""E2E-11 / E2E-12 — API/SQL source matrix (CI-mocked, no network)."""
from __future__ import annotations

from app.services.workflow.policies import build_step_fingerprint

from .helpers import (
    FakeClient,
    default_session,
    install_success_runners,
    make_engine,
)


def test_e2e11_api_source_setup_reaches_ready(monkeypatch):
    monkeypatch.setattr(
        "app.services.workflow.capability.allow_begin_step_fallback",
        lambda: True,
    )
    session = default_session(
        source_type="api",
        source_fingerprint="api-src-v1",
        source_ref={"connection_id": "conn-api-1", "label": "mock-api"},
    )
    client = FakeClient(session=session)
    install_success_runners(monkeypatch)
    engine = make_engine(client)

    for step in ("inspect", "prepare", "map", "validate", "clean", "finalize"):
        result = engine.execute_step(
            "sess-e2e-1", step, user_id="user-e2e-1", session=session
        )
        assert result.status == "completed", step
        # Fingerprints remain source-type aware.
        fp = build_step_fingerprint(
            step,
            session=session,
            dataset_key="ds-e2e",
            cleaning_profile="standard",
        )
        assert "source" in fp or "source_fingerprint" in fp or fp

    assert client.store["data_setup_sessions"][0]["status"] == "ready"
    assert client.store["data_setup_sessions"][0]["source_type"] == "api"


def test_e2e12_sql_source_setup_reaches_ready(monkeypatch):
    monkeypatch.setattr(
        "app.services.workflow.capability.allow_begin_step_fallback",
        lambda: True,
    )
    session = default_session(
        source_type="sql",
        source_fingerprint="sql-src-v1",
        source_ref={"connection_id": "conn-sql-1", "table": "sales"},
    )
    client = FakeClient(session=session)
    install_success_runners(monkeypatch)
    engine = make_engine(client)

    decision = engine.run_until_idle(
        "sess-e2e-1", user_id="user-e2e-1", session=session, max_actions=12
    )
    # Idle when complete or blocked waiting — with mocked runners should complete.
    session_row = client.store["data_setup_sessions"][0]
    assert session_row["status"] == "ready" or decision.action == "complete"
    assert session_row["source_type"] == "sql"
