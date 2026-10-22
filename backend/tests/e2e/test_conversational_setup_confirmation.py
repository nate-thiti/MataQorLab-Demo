"""E2E-02 / E2E-04 — confirmation + business-context style resolution."""
from __future__ import annotations

import pytest

from app.services.workflow.engine import ConfirmationRequired
from app.services.workflow.events import STEP_AWAITING_USER, add_event_sink, clear_event_sinks

from .helpers import (
    FakeClient,
    completed_chain,
    default_session,
    history_summary,
    install_success_runners,
    make_engine,
)


def test_e2e02_aggressive_clean_requires_confirmation_then_standard(monkeypatch):
    monkeypatch.setattr(
        "app.services.workflow.capability.allow_begin_step_fallback",
        lambda: True,
    )
    clear_event_sinks()
    events = []
    add_event_sink(events.append)

    session = default_session(cleaning_profile="aggressive")
    # Upstream complete so clean is next.
    steps = completed_chain(through="validate", session=session)
    client = FakeClient(session=session, steps=steps)
    install_success_runners(monkeypatch)
    engine = make_engine(client)

    with pytest.raises(ConfirmationRequired) as raised:
        engine.execute_step("sess-e2e-1", "clean", user_id="user-e2e-1")
    assert raised.value.decision.action == "awaiting_user"
    assert any(e.event_type == STEP_AWAITING_USER for e in events)

    # Clean tool must not have completed.
    clean_rows = [
        r for r in client.store["workflow_steps"] if r["step_type"] == "clean"
    ]
    assert all(r["status"] != "completed" for r in clean_rows)

    # Product path (orchestrator): apply Standard update, expect confirmation stale,
    # then replan and execute clean without aggressive confirmation.
    from app.services.orchestrator.session_updates import apply_context_updates

    updated = apply_context_updates(
        client,
        session_id="sess-e2e-1",
        user_id="user-e2e-1",
        session=client.store["data_setup_sessions"][0],
        context_updates={"cleaning_profile": "standard"},
    )
    assert updated["cleaning_profile"] == "standard"
    try:
        engine.resolve_awaiting_user(
            "sess-e2e-1",
            "clean",
            user_id="user-e2e-1",
            resolution={
                "decision": "modified",
                "context_updates": {"cleaning_profile": "standard"},
            },
        )
    except RuntimeError as exc:
        assert "CONFIRMATION_STALE" in str(exc)

    result = engine.execute_step(
        "sess-e2e-1", "clean", user_id="user-e2e-1", session=updated
    )
    assert result.status == "completed"

    hist = history_summary(client)
    # Confirmation pause may be marked stale after profile modify (fingerprint drift).
    assert any("clean" in h and h.split()[-1] in {"awaiting_user", "stale", "ready"} for h in hist)
    assert any("clean" in h and "completed" in h for h in hist)
    assert len([h for h in hist if h.startswith("clean ")]) >= 2


def test_e2e04_business_context_resolution_updates_contract(monkeypatch):
    monkeypatch.setattr(
        "app.services.workflow.capability.allow_begin_step_fallback",
        lambda: True,
    )
    session = default_session(
        cleaning_profile="standard",
        cleaning_recipe={
            "data_contract": {
                "row_grain": "invoice_line",
                "mapping_confirmed": True,
                "business_context_reviewed": False,
            }
        },
        source_ref={"file_name": "sales_returns.csv"},
    )
    client = FakeClient(session=session, steps=completed_chain(through="map", session=session))
    install_success_runners(monkeypatch)
    engine = make_engine(client)

    # Simulate product path: apply user-confirmed returns policy then continue.
    from app.services.orchestrator.session_updates import apply_context_updates

    refreshed = apply_context_updates(
        client,
        session_id="sess-e2e-1",
        user_id="user-e2e-1",
        session=session,
        context_updates={
            "return_policy": {
                "value": "returns",
                "treatment": "retain_negative_as_returns",
            }
        },
    )
    contract = (refreshed.get("cleaning_recipe") or {}).get("data_contract") or {}
    policy = contract.get("return_policy") or {}
    assert policy.get("source") == "user_confirmed"
    assert policy.get("value") == "returns"

    engine.sync_input_validity("sess-e2e-1", session=refreshed)
    result = engine.execute_step(
        "sess-e2e-1", "validate", user_id="user-e2e-1", session=refreshed
    )
    assert result.status == "completed"
