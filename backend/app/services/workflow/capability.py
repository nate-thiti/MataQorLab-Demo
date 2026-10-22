"""Workflow persistence capability checks (Phase 4.5).

Production requires the atomic ``begin_workflow_step`` RPC. Python fallback
is race-prone and must not silently activate in production.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger("mataqorlab.workflow.capability")

_validated_ok: bool = False
_validated_mode: Optional[str] = None


class WorkflowPersistenceError(RuntimeError):
    """Raised when required workflow DB capability is unavailable."""


def is_production_env() -> bool:
    return str(settings.APP_ENV or "").strip().lower() in {"production", "prod"}


def allow_begin_step_fallback() -> bool:
    """Whether the race-prone Python begin_step path may be used."""
    explicit = settings.WORKFLOW_ALLOW_BEGIN_STEP_FALLBACK
    if explicit is not None:
        return bool(explicit)
    return not is_production_env()


def reset_workflow_capability_cache() -> None:
    """Test helper."""
    global _validated_ok, _validated_mode
    _validated_ok = False
    _validated_mode = None


def ensure_workflow_persistence_ready(
    client: Any | None = None,
    *,
    force: bool = False,
) -> str:
    """Validate workflow_steps + RPC once per process (or when forced).

    Returns mode: ``atomic`` (RPC required/available) or ``fallback`` (dev/test).
    """
    global _validated_ok, _validated_mode
    if _validated_ok and not force and _validated_mode:
        return _validated_mode

    from app.core.supabase import get_supabase_client

    db = client or get_supabase_client()
    fallback_ok = allow_begin_step_fallback()

    try:
        db.table("workflow_steps").select("id").limit(1).execute()
    except Exception as exc:
        raise WorkflowPersistenceError(
            "WORKFLOW_STEPS_UNAVAILABLE: workflow_steps table is not accessible"
        ) from exc

    if fallback_ok:
        _validated_ok = True
        _validated_mode = "fallback"
        logger.info(
            "workflow_persistence_ready",
            extra={"mode": "fallback", "rpc_required": False},
        )
        return _validated_mode

    probe_id = str(uuid.uuid4())
    try:
        db.rpc(
            "begin_workflow_step",
            {
                "p_session_id": probe_id,
                "p_step_type": "inspect",
                "p_input": {"_capability_probe": True},
                "p_bump_version": False,
            },
        ).execute()
    except Exception as exc:
        detail = str(exc).lower()
        # Empty/missing session returns successfully with no rows — that is OK.
        # Missing function / permission errors must fail closed.
        missing = any(
            token in detail
            for token in (
                "could not find the function",
                "function public.begin_workflow_step",
                "pgrst202",
                "does not exist",
                "permission denied",
                "rpc unavailable",
            )
        )
        if missing or "begin_workflow_step" in detail:
            raise WorkflowPersistenceError(
                "WORKFLOW_RPC_UNAVAILABLE: begin_workflow_step is required in "
                "production (set WORKFLOW_ALLOW_BEGIN_STEP_FALLBACK=true only "
                "for explicit non-production use)"
            ) from exc
        # Other errors (e.g. invalid uuid cast already handled) — treat as available
        # only when the RPC endpoint responded with a business error.
        logger.warning(
            "workflow_rpc_probe_nonfatal",
            extra={"detail": str(exc)[:200]},
        )

    _validated_ok = True
    _validated_mode = "atomic"
    logger.info(
        "workflow_persistence_ready",
        extra={"mode": "atomic", "rpc_required": True},
    )
    return _validated_mode
