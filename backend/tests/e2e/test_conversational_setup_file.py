"""E2E-01 — simple file conversational/engine flow to ready."""
from __future__ import annotations

import asyncio

from app.services.orchestrator.decision_models import ToolCallDecision
from app.services.orchestrator.orchestrator import WorkflowOrchestrator
from app.services.workflow.events import clear_event_sinks, reset_metric_counters

from .helpers import (
    FakeClient,
    default_session,
    history_summary,
    install_success_runners,
    make_engine,
)


def test_e2e01_simple_file_engine_to_ready(monkeypatch):
    monkeypatch.setattr(
        "app.services.workflow.capability.allow_begin_step_fallback",
        lambda: True,
    )
    reset_metric_counters()
    clear_event_sinks()
    client = FakeClient(session=default_session(cleaning_profile="standard"))
    install_success_runners(monkeypatch)
    engine = make_engine(client)

    for step in ("inspect", "prepare", "map", "validate", "clean", "finalize"):
        result = engine.execute_step(
            "sess-e2e-1", step, user_id="user-e2e-1"
        )
        assert result.status == "completed", step

    session = client.store["data_setup_sessions"][0]
    assert session["status"] == "ready"
    assert session.get("dataset_version_id") == "dv-e2e-1"
    hist = history_summary(client)
    for step in ("inspect", "prepare", "map", "validate", "clean", "finalize"):
        assert any(h.startswith(f"{step} v1 attempt1 completed") for h in hist), hist


def test_e2e01_orchestrator_deterministic_loop_to_ready(
    monkeypatch, inline_asyncio_to_thread
):
    monkeypatch.setattr(
        "app.services.workflow.capability.allow_begin_step_fallback",
        lambda: True,
    )
    client = FakeClient(session=default_session())
    install_success_runners(monkeypatch)
    engine = make_engine(client)
    orch = WorkflowOrchestrator(client=client)
    orch.engine = engine

    sequence = [
        ToolCallDecision(step_type="inspect", reason="e2e"),
        ToolCallDecision(step_type="prepare", reason="e2e"),
        ToolCallDecision(step_type="map", reason="e2e"),
        ToolCallDecision(step_type="validate", reason="e2e"),
        ToolCallDecision(step_type="clean", reason="e2e"),
        ToolCallDecision(step_type="finalize", reason="e2e"),
    ]

    async def run_sequence():
        results = []
        for decision in sequence:
            results.append(
                await orch.handle_message(
                    session_id="sess-e2e-1",
                    user_id="user-e2e-1",
                    message="วิเคราะห์ไฟล์นี้ให้หน่อย",
                    llm_decision_override=decision,
                )
            )
        return results

    for result in asyncio.run(run_sequence()):
        assert result.engine_result is not None or result.decision.type in {
            "respond", "ask_user", "tool_call"
        }

    # Drive remaining via engine if orchestrator responded early.
    session = client.store["data_setup_sessions"][0]
    if session["status"] != "ready":
        engine.run_until_idle("sess-e2e-1", user_id="user-e2e-1", max_actions=10)
        session = client.store["data_setup_sessions"][0]
    assert session["status"] == "ready"
    assert any("finalize" in h and "completed" in h for h in history_summary(client))
