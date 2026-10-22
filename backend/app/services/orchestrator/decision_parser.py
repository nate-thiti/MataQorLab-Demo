"""Parse LLM output into OrchestratorDecision — fail closed."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from pydantic import TypeAdapter, ValidationError

from app.services.orchestrator.decision_models import (
    AskUserDecision,
    OrchestratorDecision,
    RespondDecision,
    ToolCallDecision,
)

_DECISION_ADAPTER = TypeAdapter(OrchestratorDecision)

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


class DecisionParseError(ValueError):
    pass


def _extract_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        raise DecisionParseError("Empty model output")
    fence = _FENCE_RE.search(raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise DecisionParseError("Model output is not JSON")
        try:
            parsed = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            raise DecisionParseError(f"Malformed JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise DecisionParseError("Decision root must be an object")
    return parsed


def _reject_executable_extras(payload: Dict[str, Any]) -> None:
    forbidden = {
        "function",
        "module",
        "sql",
        "shell",
        "command",
        "callback_url",
        "handler",
        "python",
        "code",
        "execute_etl_recipe",
        "tool_name",
    }
    for key in payload:
        if str(key).lower() in forbidden:
            raise DecisionParseError(f"Forbidden field in decision: {key}")
    proposed = payload.get("proposed_input")
    if isinstance(proposed, dict):
        for key in proposed:
            lowered = str(key).lower()
            if any(
                token in lowered
                for token in (
                    "password",
                    "secret",
                    "token",
                    "api_key",
                    "service_role",
                    "sql",
                    "shell",
                )
            ):
                raise DecisionParseError(f"Forbidden proposed_input field: {key}")


def parse_orchestrator_decision(text: str) -> OrchestratorDecision:
    payload = _extract_json_object(text)
    _reject_executable_extras(payload)
    decision_type = str(payload.get("type") or "").strip().lower()
    # Phase 7.2: collect_input is ask_user with a decision_key.
    if decision_type == "collect_input":
        payload = {**payload, "type": "ask_user"}
        decision_type = "ask_user"
    if decision_type not in {"ask_user", "tool_call", "respond"}:
        raise DecisionParseError(f"Unknown decision type: {decision_type or '<missing>'}")
    try:
        return _DECISION_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        raise DecisionParseError(str(exc)) from exc


def try_parse_with_repair(
    text: str,
    *,
    repair_text: Optional[str] = None,
) -> OrchestratorDecision:
    """Parse once; optionally accept a single repaired text (caller invokes LLM)."""
    try:
        return parse_orchestrator_decision(text)
    except DecisionParseError:
        if not repair_text:
            raise
        return parse_orchestrator_decision(repair_text)


def coerce_ask_user(
    question: str,
    *,
    reason: Optional[str] = None,
    context_key: Optional[str] = None,
    options: Optional[list] = None,
    decision_key: Optional[str] = None,
    expected_answer_type: Optional[str] = None,
) -> AskUserDecision:
    return AskUserDecision(
        question=question,
        reason=reason,
        context_key=context_key,
        options=options,
        decision_key=decision_key,
        expected_answer_type=expected_answer_type,
    )


def coerce_respond(message: str) -> RespondDecision:
    return RespondDecision(message=message)


def coerce_tool_call(step_type: str, reason: str = "") -> ToolCallDecision:
    return ToolCallDecision(step_type=step_type, reason=reason or f"Execute {step_type}")
