"""Service-level indicators for P2 SLO measurement."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger("mataqorlab.sli")

# Production targets documented in docs/operations/slo.md
SLO_TARGETS_MS = {
    "upload": 5_000,
    "quick_scan": 8_000,
    "etl": 120_000,
    "chat_ttfb": 3_000,
    "dashboard": 4_000,
}


@contextmanager
def measure_sli(workflow: str, *, outcome: str = "ok") -> Iterator[dict[str, float | str]]:
    started = time.perf_counter()
    meta: dict[str, float | str] = {"workflow": workflow, "outcome": outcome}
    try:
        yield meta
    except Exception:
        meta["outcome"] = "error"
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        meta["duration_ms"] = duration_ms
        target = SLO_TARGETS_MS.get(workflow)
        within_slo = True if target is None else duration_ms <= target
        logger.info(
            "sli_sample",
            extra={
                "workflow": workflow,
                "outcome": meta.get("outcome", outcome),
                "duration_ms": duration_ms,
                "slo_target_ms": target,
                "within_slo": within_slo,
            },
        )


def sli_event(
    workflow: str,
    *,
    duration_ms: float,
    outcome: str = "ok",
) -> dict[str, object]:
    target = SLO_TARGETS_MS.get(workflow)
    return {
        "event": "sli_sample",
        "workflow": workflow,
        "duration_ms": duration_ms,
        "outcome": outcome,
        "slo_target_ms": target,
        "within_slo": True if target is None else duration_ms <= target,
    }
