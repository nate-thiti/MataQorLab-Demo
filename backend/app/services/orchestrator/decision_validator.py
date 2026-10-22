"""Deterministic pre-engine validation for orchestrator decisions."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from app.services.tools.registry import UnknownStepError, resolve_step_type
from app.services.orchestrator.decision_models import (
    AskUserDecision,
    AskUserOption,
    OrchestratorDecision,
    RespondDecision,
    ToolCallDecision,
)

CANONICAL_STEPS: Set[str] = {
    "inspect",
    "prepare",
    "clean",
    "map",
    "validate",
    "finalize",
}

_MAX_OPTIONS = 8
_MAX_OPTION_LABEL = 120
_MAX_PROPOSED_KEYS = 20


class DecisionValidationError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def validate_decision(
    decision: OrchestratorDecision,
    *,
    session: Optional[Dict[str, Any]] = None,
) -> OrchestratorDecision:
    if isinstance(decision, ToolCallDecision):
        return _validate_tool_call(decision, session=session)
    if isinstance(decision, AskUserDecision):
        return _validate_ask_user(decision)
    if isinstance(decision, RespondDecision):
        if not str(decision.message or "").strip():
            raise DecisionValidationError("EMPTY_RESPONSE", "respond.message is empty")
        return decision
    raise DecisionValidationError("UNKNOWN_DECISION", "Unsupported decision type")


def _validate_tool_call(
    decision: ToolCallDecision,
    *,
    session: Optional[Dict[str, Any]],
) -> ToolCallDecision:
    try:
        step = resolve_step_type(decision.step_type)
    except UnknownStepError as exc:
        raise DecisionValidationError("UNKNOWN_STEP", str(exc)) from exc
    if step not in CANONICAL_STEPS:
        raise DecisionValidationError("UNKNOWN_STEP", f"Step not allowed: {step}")
    if session is None:
        raise DecisionValidationError("SESSION_MISSING", "Setup session not found")
    proposed = dict(decision.proposed_input or {})
    if len(proposed) > _MAX_PROPOSED_KEYS:
        raise DecisionValidationError("PROPOSED_INPUT_TOO_LARGE", "proposed_input too large")
    # Only allowlisted session-safe metadata; orchestrator applies cleaning_profile.
    cleaned: Dict[str, Any] = {}
    for key, value in proposed.items():
        key_s = str(key)
        lowered = key_s.lower()
        if any(tok in lowered for tok in ("password", "secret", "token", "sql", "shell")):
            raise DecisionValidationError(
                "FORBIDDEN_INPUT", f"Forbidden proposed_input key: {key_s}"
            )
        if key_s not in {"cleaning_profile"}:
            # Ignore non-executable metadata rather than failing the turn.
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[key_s] = value
        else:
            cleaned[key_s] = str(value)[:200]
    return ToolCallDecision(
        step_type=step,
        reason=str(decision.reason or "")[:500],
        proposed_input=cleaned,
    )


def _validate_ask_user(decision: AskUserDecision) -> AskUserDecision:
    if not str(decision.question or "").strip():
        raise DecisionValidationError("EMPTY_QUESTION", "ask_user.question is empty")
    options = decision.options or []
    if len(options) > _MAX_OPTIONS:
        raise DecisionValidationError("TOO_MANY_OPTIONS", "Too many ask_user options")
    cleaned_options = []
    for opt in options:
        oid = str(getattr(opt, "id", None) or (opt.get("id") if isinstance(opt, dict) else "")).strip()
        label = str(
            getattr(opt, "label", None) or (opt.get("label") if isinstance(opt, dict) else "")
        ).strip()
        if not oid or not label:
            raise DecisionValidationError("INVALID_OPTION", "Option id/label required")
        if len(label) > _MAX_OPTION_LABEL:
            label = label[:_MAX_OPTION_LABEL]
        # Reject options that encode executable actions.
        if any(tok in oid.lower() for tok in ("sql", "shell", "exec", "http")):
            raise DecisionValidationError("INVALID_OPTION", f"Unsupported option id: {oid}")
        cleaned_options.append(AskUserOption(id=oid, label=label))
    return AskUserDecision(
        question=decision.question.strip()[:2000],
        reason=(decision.reason or None),
        context_key=decision.context_key,
        decision_key=decision.decision_key or decision.context_key,
        expected_answer_type=decision.expected_answer_type,
        options=cleaned_options or None,
    )
