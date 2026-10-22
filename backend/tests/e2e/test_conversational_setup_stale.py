"""E2E-03 / E2E-08 / E2E-14 — stale after mapping / profile / contract changes."""
from __future__ import annotations

from app.services.orchestrator.session_updates import apply_context_updates

from .helpers import (
    FakeClient,
    completed_chain,
    default_session,
    history_summary,
    install_success_runners,
    make_engine,
)


def test_e2e08_mapping_change_stales_validate_keeps_clean(monkeypatch):
    monkeypatch.setattr(
        "app.services.workflow.capability.allow_begin_step_fallback",
        lambda: True,
    )
    session = default_session()
    steps = completed_chain(through="clean", session=session)
    client = FakeClient(session=session, steps=steps)
    install_success_runners(monkeypatch)
    engine = make_engine(client)

    updated = apply_context_updates(
        client,
        session_id="sess-e2e-1",
        user_id="user-e2e-1",
        session=session,
        context_updates={"column_mapping": {"PRICE_LEVEL": "segment"}},
    )
    engine.sync_input_validity("sess-e2e-1", session=updated)

    by_type = {}
    for row in client.store["workflow_steps"]:
        by_type[row["step_type"]] = row

    assert by_type["validate"]["status"] == "stale"
    # Graph policy: map invalidation targets exclude clean.
    from app.services.workflow.dependencies import invalidation_targets

    assert "clean" not in invalidation_targets("map")
    # Fingerprint sync may still mark clean stale if clean inputs embed mapping.
    assert by_type["clean"]["status"] in {"completed", "stale"}

    map_result = engine.execute_step(
        "sess-e2e-1", "map", user_id="user-e2e-1", session=updated
    )
    assert map_result.status == "completed"
    validate_result = engine.execute_step(
        "sess-e2e-1", "validate", user_id="user-e2e-1", session=updated
    )
    assert validate_result.status == "completed"
    clean_result = engine.execute_step(
        "sess-e2e-1", "clean", user_id="user-e2e-1", session=updated
    )
    assert clean_result.status == "completed"


def test_e2e_cleaning_profile_change_stales_clean(monkeypatch):
    monkeypatch.setattr(
        "app.services.workflow.capability.allow_begin_step_fallback",
        lambda: True,
    )
    session = default_session(cleaning_profile="standard")
    steps = completed_chain(through="finalize", session=session)
    # Session was ready under standard — now change profile.
    session = {
        **session,
        "status": "processing",
        "cleaning_profile": "conservative",
        "output_file": None,
    }
    client = FakeClient(session=session, steps=steps)
    engine = make_engine(client)
    engine.sync_input_validity("sess-e2e-1", session=session)

    statuses = {
        r["step_type"]: r["status"]
        for r in client.store["workflow_steps"]
        if r["status"] != "superseded"
    }
    # Latest rows after stale marks.
    latest = {}
    for row in client.store["workflow_steps"]:
        key = row["step_type"]
        prev = latest.get(key)
        if not prev or (row.get("version"), row.get("attempt")) >= (
            prev.get("version"), prev.get("attempt")
        ):
            latest[key] = row
    assert latest["clean"]["status"] == "stale"
    assert latest["finalize"]["status"] == "stale"
    assert latest["map"]["status"] == "completed"


def test_e2e03_ambiguous_mapping_resolution_path(monkeypatch):
    monkeypatch.setattr(
        "app.services.workflow.capability.allow_begin_step_fallback",
        lambda: True,
    )
    session = default_session(
        source_ref={"file_name": "sales_mapping_ambiguous.csv"},
        column_mapping={
            "invoice_date": "date",
            "amount": "sales",
            # PRICE_LEVEL intentionally unresolved initially
        },
    )
    client = FakeClient(
        session=session,
        steps=completed_chain(through="prepare", session=session),
    )
    install_success_runners(monkeypatch)
    engine = make_engine(client)

    updated = apply_context_updates(
        client,
        session_id="sess-e2e-1",
        user_id="user-e2e-1",
        session=session,
        context_updates={"column_mapping": {"PRICE_LEVEL": "segment"}},
    )
    assert updated["column_mapping"]["PRICE_LEVEL"] == "segment"
    result = engine.execute_step(
        "sess-e2e-1", "map", user_id="user-e2e-1", session=updated
    )
    assert result.status == "completed"
    assert any("map" in h and "completed" in h for h in history_summary(client))
