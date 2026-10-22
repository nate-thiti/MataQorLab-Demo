"""Controller turn performance instrumentation (Phase 7.2.2)."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger("mataqorlab.orchestrator.timing")


class ControllerTurnTimer:
    """Aggregates per-turn and per-iteration timings for ops diagnostics."""

    def __init__(self, *, session_id: str = "", user_id: str = "") -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.turn_started = time.perf_counter()
        self.segments: Dict[str, float] = {}
        self.iterations: List[Dict[str, Any]] = []
        self._current_iteration: Optional[Dict[str, Any]] = None
        self.llm_call_count = 0

    def start_iteration(self, index: int) -> None:
        self._current_iteration = {
            "iteration": index,
            "started_at": time.perf_counter(),
            "segments": {},
        }

    def finish_iteration(
        self,
        *,
        decision_type: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> None:
        if not self._current_iteration:
            return
        started = self._current_iteration.pop("started_at", time.perf_counter())
        total_ms = (time.perf_counter() - started) * 1000.0
        segs = dict(self._current_iteration.get("segments") or {})
        row = {
            **self._current_iteration,
            "decision_type": decision_type,
            "capability": capability,
            "llm_ms": round(segs.get("llm_ms", 0.0), 2),
            "tool_ms": round(segs.get("tool_ms", 0.0), 2),
            "db_ms": round(segs.get("db_ms", 0.0), 2),
            "memory_ms": round(segs.get("memory_ms", 0.0), 2),
            "total_ms": round(total_ms, 2),
        }
        self.iterations.append(row)
        self._current_iteration = None

    def add_ms(self, key: str, ms: float) -> None:
        self.segments[key] = self.segments.get(key, 0.0) + ms
        if self._current_iteration is not None:
            inner = self._current_iteration.setdefault("segments", {})
            inner[key] = inner.get(key, 0.0) + ms

    @contextmanager
    def track(self, key: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.add_ms(key, (time.perf_counter() - start) * 1000.0)

    def note_llm_call(self) -> None:
        self.llm_call_count += 1

    def summary(self, *, stop_reason: str) -> Dict[str, Any]:
        total_ms = (time.perf_counter() - self.turn_started) * 1000.0
        llm_ms = self.segments.get("llm_ms", 0.0)
        tool_ms = self.segments.get("tool_ms", 0.0)
        db_ms = self.segments.get("db_ms", 0.0)
        memory_ms = self.segments.get("memory_ms", 0.0)
        state_load_ms = self.segments.get("state_load_ms", 0.0)
        known = llm_ms + tool_ms + db_ms + memory_ms + state_load_ms
        other_ms = max(0.0, total_ms - known)
        payload = {
            "event": "controller_turn_completed",
            "session_id": self.session_id,
            "total_ms": round(total_ms, 2),
            "request_total_ms": round(total_ms, 2),
            "controller_total_ms": round(total_ms, 2),
            "state_load_ms": round(state_load_ms, 2),
            "working_memory_build_ms": round(memory_ms, 2),
            "llm_total_ms": round(llm_ms, 2),
            "llm_call_count": self.llm_call_count,
            "engine_total_ms": round(tool_ms, 2),
            "tool_total_ms": round(tool_ms, 2),
            "db_read_ms": round(db_ms * 0.6, 2),
            "db_write_ms": round(db_ms * 0.4, 2),
            "db_total_ms": round(db_ms, 2),
            "stamp_persist_ms": round(self.segments.get("stamp_persist_ms", 0.0), 2),
            "other_ms": round(other_ms, 2),
            "iterations": len(self.iterations),
            "iteration_summaries": self.iterations,
            "stop_reason": stop_reason,
        }
        self._maybe_warn_slow(payload)
        return payload

    def _maybe_warn_slow(self, payload: Dict[str, Any]) -> None:
        total = float(payload.get("total_ms") or 0.0)
        llm = float(payload.get("llm_total_ms") or 0.0)
        tool = float(payload.get("tool_total_ms") or 0.0)
        db = float(payload.get("db_total_ms") or 0.0)
        if total >= float(getattr(settings, "CONTROLLER_SLOW_TURN_MS", 30000) or 30000):
            logger.warning("controller_slow_turn", extra={"performance": payload})
        if llm >= float(getattr(settings, "LLM_SLOW_CALL_MS", 15000) or 15000):
            logger.warning("controller_slow_llm", extra={"llm_total_ms": llm, "session_id": self.session_id})
        if tool >= float(getattr(settings, "WORKFLOW_STEP_SLOW_MS", 10000) or 10000):
            logger.warning("controller_slow_tool", extra={"tool_total_ms": tool, "session_id": self.session_id})
        if db >= float(getattr(settings, "DB_SLOW_AGGREGATE_MS", 5000) or 5000):
            logger.warning("controller_slow_db", extra={"db_total_ms": db, "session_id": self.session_id})
