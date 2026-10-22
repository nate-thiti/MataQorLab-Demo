"""Workflow health, stuck detection, and timing helpers (Phase 7).

Diagnostic only — never mutates workflow state.
"""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, Iterable, List, Mapping, Optional

from app.core.config import settings
from app.services.workflow.events import get_metric_counters


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _age_minutes(ts: Optional[datetime], *, now: Optional[datetime] = None) -> Optional[float]:
    if not ts:
        return None
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - ts).total_seconds() / 60.0)


def find_stuck_workflows(
    sessions: Iterable[Mapping[str, Any]],
    steps: Iterable[Mapping[str, Any]] | None = None,
    *,
    running_stuck_minutes: Optional[float] = None,
    awaiting_user_stale_hours: Optional[float] = None,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Identify potentially stuck workflows without changing state."""
    running_threshold = float(
        running_stuck_minutes
        if running_stuck_minutes is not None
        else settings.WORKFLOW_RUNNING_STUCK_MINUTES
    )
    awaiting_threshold_min = float(
        (awaiting_user_stale_hours
         if awaiting_user_stale_hours is not None
         else settings.WORKFLOW_AWAITING_USER_STALE_HOURS) * 60.0
    )
    now = now or datetime.now(timezone.utc)
    steps_by_session: Dict[str, List[Mapping[str, Any]]] = {}
    for row in steps or []:
        sid = str(row.get("data_setup_session_id") or "")
        if sid:
            steps_by_session.setdefault(sid, []).append(row)

    stuck: List[Dict[str, Any]] = []
    for session in sessions:
        sid = str(session.get("id") or "")
        if not sid:
            continue
        status = str(session.get("status") or "")
        if status in {"ready", "cancelled"}:
            continue
        session_steps = steps_by_session.get(sid) or []
        reasons: List[str] = []

        for step in session_steps:
            st = str(step.get("status") or "")
            updated = _parse_ts(step.get("updated_at") or step.get("created_at"))
            age = _age_minutes(updated, now=now)
            if st == "running" and age is not None and age >= running_threshold:
                reasons.append(
                    f"step:{step.get('step_type')}:running>{running_threshold:.0f}m"
                )
            if st == "awaiting_user" and age is not None and age >= awaiting_threshold_min:
                reasons.append(
                    f"step:{step.get('step_type')}:awaiting_user>"
                    f"{awaiting_threshold_min / 60.0:.1f}h"
                )
            if st == "failed" and not bool(step.get("retryable", True)):
                # Failed latest non-retryable — surface for ops.
                reasons.append(f"step:{step.get('step_type')}:failed_non_retryable")
            if st == "ready":
                # Approved confirmation waiting with no execution progress.
                age_ready = _age_minutes(updated, now=now)
                if age_ready is not None and age_ready >= running_threshold:
                    reasons.append(
                        f"step:{step.get('step_type')}:approved_idle>{running_threshold:.0f}m"
                    )

        progress = session.get("processing_progress") or {}
        if isinstance(progress, Mapping) and progress.get("stage") == "awaiting_user":
            updated = _parse_ts(session.get("updated_at") or session.get("created_at"))
            age = _age_minutes(updated, now=now)
            if age is not None and age >= awaiting_threshold_min:
                reasons.append("session:awaiting_user_stale")

        if status == "failed":
            reasons.append("session:failed")

        if reasons:
            stuck.append({
                "session_id": sid,
                "user_id": session.get("user_id"),
                "status": status,
                "source_type": session.get("source_type"),
                "reasons": sorted(set(reasons)),
            })
    return stuck


def compute_awaiting_user_ms(
    steps: Iterable[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> int:
    """Sum time spent in awaiting_user across step rows (best-effort)."""
    now = now or datetime.now(timezone.utc)
    total = 0
    for step in steps:
        if str(step.get("status")) != "awaiting_user":
            # Prefer explicit timestamps if present in output metadata.
            output = step.get("output") or {}
            meta = output.get("metadata") if isinstance(output, dict) else {}
            started = _parse_ts((meta or {}).get("awaiting_started_at"))
            ended = _parse_ts((meta or {}).get("awaiting_resolved_at"))
            if started and ended:
                total += max(0, int((ended - started).total_seconds() * 1000))
            continue
        started = _parse_ts(step.get("updated_at") or step.get("created_at"))
        if started:
            total += max(0, int((now - started).total_seconds() * 1000))
    return total


def compute_workflow_durations(session: Mapping[str, Any]) -> Dict[str, Optional[int]]:
    started = _parse_ts(session.get("created_at") or session.get("started_at"))
    ready = None
    if str(session.get("status")) == "ready":
        ready = _parse_ts(session.get("updated_at") or session.get("ready_at"))
    total_ms = None
    if started and ready:
        total_ms = max(0, int((ready - started).total_seconds() * 1000))
    return {
        "workflow_started_at": started.isoformat() if started else None,
        "workflow_ready_at": ready.isoformat() if ready else None,
        "total_elapsed_ms": total_ms,
    }


def build_workflow_health_summary(
    sessions: Iterable[Mapping[str, Any]],
    steps: Iterable[Mapping[str, Any]] | None = None,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Aggregate internal health summary (admin/ops only)."""
    sessions = list(sessions)
    steps = list(steps or [])
    counts = {
        "workflows": len(sessions),
        "ready": 0,
        "failed": 0,
        "awaiting_user": 0,
        "running": 0,
        "processing": 0,
        "cancelled": 0,
        "other": 0,
    }
    setup_durations: List[int] = []
    for session in sessions:
        status = str(session.get("status") or "other")
        if status == "ready":
            counts["ready"] += 1
            dur = compute_workflow_durations(session).get("total_elapsed_ms")
            if isinstance(dur, int):
                setup_durations.append(dur)
        elif status == "failed":
            counts["failed"] += 1
        elif status in {"awaiting_answers", "awaiting_user"}:
            counts["awaiting_user"] += 1
        elif status == "processing":
            # Distinguish active running steps below.
            counts["processing"] += 1
        elif status == "cancelled":
            counts["cancelled"] += 1
        else:
            counts["other"] += 1

    step_failures: Dict[str, int] = {}
    retries: Dict[str, int] = {}
    running_steps = 0
    for step in steps:
        st = str(step.get("status") or "")
        step_type = str(step.get("step_type") or "unknown")
        if st == "failed":
            step_failures[step_type] = step_failures.get(step_type, 0) + 1
        if st == "running":
            running_steps += 1
        attempt = int(step.get("attempt") or 1)
        if attempt > 1:
            retries[step_type] = retries.get(step_type, 0) + (attempt - 1)

    counts["running"] = running_steps
    stuck = find_stuck_workflows(sessions, steps, now=now)
    counters = get_metric_counters()

    return {
        **counts,
        "median_setup_ms": int(median(setup_durations)) if setup_durations else None,
        "step_failures": step_failures,
        "step_retries": retries,
        "stuck_workflows": len(stuck),
        "stuck_samples": stuck[:20],
        "process_counters": {
            k: v for k, v in counters.items()
            if k.startswith(("event:", "decision:", "step_failure:", "step_retry:"))
            or k == "awaiting_user_questions"
        },
        "thresholds": {
            "running_stuck_minutes": settings.WORKFLOW_RUNNING_STUCK_MINUTES,
            "awaiting_user_stale_hours": settings.WORKFLOW_AWAITING_USER_STALE_HOURS,
        },
    }


def summarize_session_observability(
    session: Mapping[str, Any],
    steps: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Per-session observability snapshot for diagnostics."""
    steps = list(steps)
    durations = compute_workflow_durations(session)
    awaiting_ms = compute_awaiting_user_ms(steps)
    processing_ms = None
    if durations.get("total_elapsed_ms") is not None:
        processing_ms = max(0, int(durations["total_elapsed_ms"]) - awaiting_ms)
    question_count = sum(
        1 for s in steps if str(s.get("status")) == "awaiting_user"
    ) + sum(
        1
        for s in steps
        if isinstance(s.get("output"), dict)
        and str((s.get("output") or {}).get("status")) == "awaiting_user"
    )
    # Prefer distinct awaiting rows by version.
    awaiting_rows = [
        s for s in steps
        if str(s.get("status")) == "awaiting_user"
        or str((s.get("output") or {}).get("status") if isinstance(s.get("output"), dict) else "")
        == "awaiting_user"
    ]
    return {
        "session_id": session.get("id"),
        "status": session.get("status"),
        "source_type": session.get("source_type"),
        **durations,
        "awaiting_user_ms": awaiting_ms,
        "processing_ms": processing_ms,
        "question_count": len({(s.get("step_type"), s.get("version"), s.get("attempt")) for s in awaiting_rows}),
        "retry_counts": {
            str(s.get("step_type")): int(s.get("attempt") or 1) - 1
            for s in steps
            if int(s.get("attempt") or 1) > 1
        },
    }
