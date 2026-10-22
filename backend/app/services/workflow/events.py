"""Lightweight structured workflow events (Phase 7 observability).

Not a message bus — emit to structured logs (+ optional in-process sink for tests).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("mataqorlab.workflow.events")

# Safe event types used across engine/orchestrator.
WORKFLOW_STARTED = "workflow_started"
STEP_STARTED = "step_started"
STEP_COMPLETED = "step_completed"
STEP_FAILED = "step_failed"
STEP_RETRIED = "step_retried"
STEP_REUSED = "step_reused"
STEP_AWAITING_USER = "step_awaiting_user"
STEP_RESOLVED = "step_resolved"
STEP_STALE = "step_stale"
WORKFLOW_READY = "workflow_ready"
WORKFLOW_BLOCKED = "workflow_blocked"
ORCHESTRATOR_DECISION = "orchestrator_decision"
ORCHESTRATOR_FALLBACK = "orchestrator_fallback"
ORCHESTRATOR_ENGINE_REJECTION = "orchestrator_engine_rejection"
ORCHESTRATOR_LLM_FAILED = "orchestrator_llm_failed"
ORCHESTRATOR_MALFORMED = "orchestrator_malformed_decision"


class WorkflowEvent(BaseModel):
    event_type: str
    session_id: str
    step_type: Optional[str] = None
    status: Optional[str] = None
    version: Optional[int] = None
    attempt: Optional[int] = None
    duration_ms: Optional[int] = None
    reason_code: Optional[str] = None
    source_type: Optional[str] = None
    decision_type: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)


_sinks: List[Callable[[WorkflowEvent], None]] = []
_sink_lock = threading.Lock()
_counters: Dict[str, int] = {}
_counter_lock = threading.Lock()


def add_event_sink(sink: Callable[[WorkflowEvent], None]) -> None:
    with _sink_lock:
        _sinks.append(sink)


def clear_event_sinks() -> None:
    with _sink_lock:
        _sinks.clear()


def reset_metric_counters() -> None:
    with _counter_lock:
        _counters.clear()


def get_metric_counters() -> Dict[str, int]:
    with _counter_lock:
        return dict(_counters)


def _bump(key: str, n: int = 1) -> None:
    with _counter_lock:
        _counters[key] = int(_counters.get(key) or 0) + n


def emit_workflow_event(
    event_type: str,
    *,
    session_id: str,
    step_type: Optional[str] = None,
    status: Optional[str] = None,
    version: Optional[int] = None,
    attempt: Optional[int] = None,
    duration_ms: Optional[int] = None,
    reason_code: Optional[str] = None,
    source_type: Optional[str] = None,
    decision_type: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> WorkflowEvent:
    """Emit a bounded structured workflow event (no datasets/credentials/prompts)."""
    safe_meta: Dict[str, Any] = {}
    for k, v in dict(metadata or {}).items():
        key = str(k).lower()
        if any(part in key for part in ("path", "secret", "token", "credential", "prompt", "password")):
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            if isinstance(v, str) and len(v) > 240:
                v = v[:240]
            safe_meta[k] = v

    event = WorkflowEvent(
        event_type=event_type,
        session_id=str(session_id),
        step_type=step_type,
        status=status,
        version=int(version) if version is not None else None,
        attempt=int(attempt) if attempt is not None else None,
        duration_ms=int(duration_ms) if duration_ms is not None else None,
        reason_code=reason_code,
        source_type=source_type,
        decision_type=decision_type,
        metadata=safe_meta,
    )
    _bump(f"event:{event_type}")
    if decision_type:
        _bump(f"decision:{decision_type}")
    if step_type and event_type == STEP_FAILED:
        _bump(f"step_failure:{step_type}")
    if event_type == STEP_RETRIED and step_type:
        _bump(f"step_retry:{step_type}")
    if event_type == STEP_AWAITING_USER:
        _bump("awaiting_user_questions")

    logger.info(
        event_type,
        extra={
            "session_id": event.session_id,
            "step_type": event.step_type,
            "status": event.status,
            "version": event.version,
            "attempt": event.attempt,
            "duration_ms": event.duration_ms,
            "reason_code": event.reason_code,
            "source_type": event.source_type,
            "decision_type": event.decision_type,
            "event": event.event_type,
            **{f"meta_{k}": v for k, v in event.metadata.items()},
        },
    )
    with _sink_lock:
        sinks = list(_sinks)
    for sink in sinks:
        try:
            sink(event)
        except Exception:
            pass
    return event


class timed_step:
    """Context manager measuring step duration_ms."""

    def __init__(
        self,
        *,
        session_id: str,
        step_type: str,
        source_type: Optional[str] = None,
        version: Optional[int] = None,
        attempt: Optional[int] = None,
        is_retry: bool = False,
    ):
        self.session_id = session_id
        self.step_type = step_type
        self.source_type = source_type
        self.version = version
        self.attempt = attempt
        self.is_retry = is_retry
        self._t0 = 0.0
        self.duration_ms = 0

    def __enter__(self):
        self._t0 = time.perf_counter()
        emit_workflow_event(
            STEP_RETRIED if self.is_retry else STEP_STARTED,
            session_id=self.session_id,
            step_type=self.step_type,
            source_type=self.source_type,
            version=self.version,
            attempt=self.attempt,
        )
        return self

    def __exit__(self, exc_type, exc, _tb):
        self.duration_ms = int((time.perf_counter() - self._t0) * 1000)
        if exc_type is None:
            emit_workflow_event(
                STEP_COMPLETED,
                session_id=self.session_id,
                step_type=self.step_type,
                status="completed",
                source_type=self.source_type,
                version=self.version,
                attempt=self.attempt,
                duration_ms=self.duration_ms,
            )
        else:
            emit_workflow_event(
                STEP_FAILED,
                session_id=self.session_id,
                step_type=self.step_type,
                status="failed",
                source_type=self.source_type,
                version=self.version,
                attempt=self.attempt,
                duration_ms=self.duration_ms,
                reason_code=type(exc).__name__ if exc else "error",
                metadata={"error": str(exc)[:200] if exc else None},
            )
        return False
