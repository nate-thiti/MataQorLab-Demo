"""Phase 7 — workflow events, stuck detection, health summary."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.workflow.events import (
    ORCHESTRATOR_FALLBACK,
    STEP_COMPLETED,
    STEP_STARTED,
    add_event_sink,
    clear_event_sinks,
    emit_workflow_event,
    get_metric_counters,
    reset_metric_counters,
    timed_step,
)
from app.services.workflow.observability import (
    build_workflow_health_summary,
    compute_awaiting_user_ms,
    find_stuck_workflows,
    summarize_session_observability,
)


def test_emit_workflow_event_strips_sensitive_metadata():
    reset_metric_counters()
    clear_event_sinks()
    captured = []
    add_event_sink(captured.append)
    event = emit_workflow_event(
        STEP_STARTED,
        session_id="s1",
        step_type="clean",
        metadata={
            "storage_path": "/secret/path",
            "columns": 12,
            "token": "abc",
        },
    )
    assert "storage_path" not in event.metadata
    assert "token" not in event.metadata
    assert event.metadata.get("columns") == 12
    assert get_metric_counters()["event:step_started"] == 1
    assert captured[0].event_type == STEP_STARTED


def test_timed_step_records_duration():
    reset_metric_counters()
    clear_event_sinks()
    with timed_step(session_id="s1", step_type="inspect") as timer:
        pass
    assert timer.duration_ms >= 0
    assert get_metric_counters()["event:step_completed"] == 1


def test_find_stuck_workflows_running_and_awaiting():
    now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    sessions = [
        {"id": "s-run", "status": "processing", "user_id": "u1"},
        {"id": "s-wait", "status": "awaiting_answers", "user_id": "u1"},
        {"id": "s-ok", "status": "ready", "user_id": "u1"},
    ]
    steps = [
        {
            "data_setup_session_id": "s-run",
            "step_type": "clean",
            "status": "running",
            "updated_at": (now - timedelta(minutes=200)).isoformat(),
            "retryable": True,
        },
        {
            "data_setup_session_id": "s-wait",
            "step_type": "clean",
            "status": "awaiting_user",
            "updated_at": (now - timedelta(hours=30)).isoformat(),
            "retryable": False,
        },
    ]
    stuck = find_stuck_workflows(
        sessions,
        steps,
        running_stuck_minutes=120,
        awaiting_user_stale_hours=24,
        now=now,
    )
    ids = {item["session_id"] for item in stuck}
    assert "s-run" in ids
    assert "s-wait" in ids
    assert "s-ok" not in ids


def test_health_summary_and_session_observability():
    now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    sessions = [
        {
            "id": "s1",
            "status": "ready",
            "created_at": (now - timedelta(minutes=10)).isoformat(),
            "updated_at": now.isoformat(),
            "source_type": "file",
        },
        {
            "id": "s2",
            "status": "failed",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "source_type": "api",
        },
        {
            "id": "s3",
            "status": "awaiting_answers",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "source_type": "file",
        },
    ]
    steps = [
        {
            "data_setup_session_id": "s2",
            "step_type": "clean",
            "status": "failed",
            "attempt": 2,
            "updated_at": now.isoformat(),
        },
        {
            "data_setup_session_id": "s3",
            "step_type": "map",
            "status": "awaiting_user",
            "attempt": 1,
            "updated_at": (now - timedelta(minutes=5)).isoformat(),
        },
    ]
    reset_metric_counters()
    emit_workflow_event(ORCHESTRATOR_FALLBACK, session_id="s3", reason_code="llm_unavailable")
    summary = build_workflow_health_summary(sessions, steps, now=now)
    assert summary["workflows"] == 3
    assert summary["ready"] == 1
    assert summary["failed"] == 1
    assert summary["awaiting_user"] == 1
    assert summary["step_failures"]["clean"] == 1
    assert summary["median_setup_ms"] == 10 * 60 * 1000
    assert summary["process_counters"].get("event:orchestrator_fallback") == 1

    # Use wall-clock-relative stamps so awaiting duration is non-zero in CI.
    wall = datetime.now(timezone.utc)
    live_steps = [
        {
            "data_setup_session_id": "s3",
            "step_type": "map",
            "status": "awaiting_user",
            "attempt": 1,
            "updated_at": (wall - timedelta(minutes=5)).isoformat(),
        }
    ]
    obs = summarize_session_observability(sessions[2], live_steps)
    assert obs["awaiting_user_ms"] >= 4 * 60 * 1000
    assert obs["question_count"] >= 1
    assert compute_awaiting_user_ms(live_steps, now=wall) >= 4 * 60 * 1000
