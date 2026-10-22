"""Phase 7.2.2 — controller timing."""
from __future__ import annotations

from app.services.orchestrator.timing import ControllerTurnTimer


def test_controller_turn_timer_summary():
    timer = ControllerTurnTimer(session_id="s1", user_id="u1")
    timer.start_iteration(1)
    timer.add_ms("llm_ms", 1200.0)
    timer.add_ms("tool_ms", 400.0)
    timer.add_ms("db_ms", 150.0)
    timer.note_llm_call()
    timer.finish_iteration(decision_type="tool_call", capability="prepare")
    summary = timer.summary(stop_reason="awaiting_user")
    assert summary["event"] == "controller_turn_completed"
    assert summary["llm_call_count"] == 1
    assert summary["llm_total_ms"] == 1200.0
    assert summary["tool_total_ms"] == 400.0
    assert summary["stop_reason"] == "awaiting_user"
    assert summary["iterations"] == 1


def test_plan_has_executable_next():
    from app.services.orchestrator.orchestrator import WorkflowOrchestrator

    assert WorkflowOrchestrator._plan_has_executable_next({
        "next_action": {"action": "execute", "step_type": "map"},
    })
    assert not WorkflowOrchestrator._plan_has_executable_next({
        "awaiting_user": {"question": "?"},
        "next_action": {"action": "execute", "step_type": "map"},
    })
