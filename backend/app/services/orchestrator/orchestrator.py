"""AI Orchestrator — conversational layer over WorkflowEngine (Phase 5).

The LLM proposes structured decisions. WorkflowEngine remains authoritative.
Never call raw setup tools or execute_etl_recipe from this module.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Mapping, Optional

from app.core.config import settings
from app.core.supabase import get_supabase_client
from app.services.chat.llm_client import LlmClient
from app.services.orchestrator.answer_apply import (
    apply_decision_answer,
    build_active_decision_payload,
    normalize_active_decision_options,
    parse_simple_answer,
    persist_active_decision_and_stamps,
    persist_stamps_only,
    validate_active_decision_completeness,
)
from app.services.orchestrator.decision_identity import (
    is_decision_confirmed,
    is_original_prompt_capture,
)
from app.services.orchestrator.context_builder import build_orchestrator_llm_context
from app.services.orchestrator.timing import ControllerTurnTimer
from app.services.orchestrator.decision_models import (
    AskUserDecision,
    OrchestratorResult,
    RespondDecision,
    ToolCallDecision,
    UserResolutionProposal,
)
from app.services.orchestrator.decision_parser import (
    DecisionParseError,
    coerce_ask_user,
    coerce_respond,
    coerce_tool_call,
    parse_orchestrator_decision,
)
from app.services.orchestrator.decision_validator import (
    DecisionValidationError,
    validate_decision,
)
from app.services.orchestrator.prompts import (
    MATAQOR_ORCHESTRATOR_PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_user_prompt,
    template_for_reason_code,
)
from app.services.orchestrator.resolution import parse_user_resolution
from app.services.orchestrator.session_updates import apply_context_updates
from app.services.orchestrator.stamps import build_tool_stamp, stamp_to_dict
from app.services.orchestrator.unresolved import (
    resolve_unresolved_decisions,
    select_one_decision,
    strip_raw_validator_checklist,
    _question_for,
)
from app.services.orchestrator.working_memory import (
    build_working_memory,
    memory_for_prompt,
    next_unresolved,
)
from app.services.tools.types import ToolResult
from app.services.workflow.engine import ConfirmationRequired, WorkflowEngine
from app.services.orchestrator.usage import (
    settle_orchestrator_usage,
    summarize_calls,
)
from app.services.workflow.events import (
    ORCHESTRATOR_DECISION,
    ORCHESTRATOR_ENGINE_REJECTION,
    ORCHESTRATOR_FALLBACK,
    ORCHESTRATOR_LLM_FAILED,
    ORCHESTRATOR_MALFORMED,
    STEP_AWAITING_USER,
    WORKFLOW_READY,
    emit_workflow_event,
)

logger = logging.getLogger("mataqorlab.orchestrator")

# Engine ConfirmationRequired only — never contract collect keys like
# business_context_reviewed / mapping_confirmed (those use collect_input).
_ENGINE_CONFIRMATION_KEYS = frozenset({
    "cleaning_confirmation",
    "destructive_transform_confirmation",
    "confirmation",
    "mapping_confirmation",
    "contract_confirmation",
})
_ENGINE_CONFIRMATION_REASONS = frozenset({
    "AGGRESSIVE_CLEANING",
    "DESTRUCTIVE_TRANSFORM",
    "CONFIRMATION_REQUIRED",
    "AMBIGUOUS_MAPPING",
    "BUSINESS_CONTRACT_CHANGE",
})
_CONTRACT_COLLECT_KEYS = frozenset({
    "row_grain",
    "primary_metric",
    "metric_definition",
    "business_purpose",
    "data_owner",
    "reporting_period_status",
    "period_status",
    "return_policy",
    "cancellation_policy",
    "mapping_confirmed",
    "business_context_reviewed",
})
_ENGINE_RESOLUTION_VALUES = frozenset({
    "approve", "approved", "reject", "rejected", "modify", "modified", "ambiguous",
})
_RESOLUTION_ALIASES = {
    "approve": "approved",
    "reject": "rejected",
    "modify": "modified",
}
_SAFE_PROPOSED_INPUT_KEYS = frozenset({"cleaning_profile"})


def _normalize_resolution_decision(raw: Any) -> Optional[str]:
    value = str(raw or "").strip().lower()
    if not value:
        return None
    value = _RESOLUTION_ALIASES.get(value, value)
    if value in {"approved", "rejected", "modified", "ambiguous"}:
        return value
    return None


def _is_contract_collect_key(decision_key: str) -> bool:
    key = str(decision_key or "").strip()
    if not key:
        return False
    if key in _CONTRACT_COLLECT_KEYS:
        return True
    return key.startswith("mapping:")


def _is_engine_confirmation_decision(
    active: Optional[Mapping[str, Any]],
    decision_key: str = "",
) -> bool:
    key = str(
        decision_key
        or (active or {}).get("decision_key")
        or ""
    ).strip()
    # Contract collect questions must never be treated as engine confirmations,
    # even if the LLM reused a confirmation reason_code.
    if _is_contract_collect_key(key):
        return False
    if key in _ENGINE_CONFIRMATION_KEYS:
        return True
    reason = str((active or {}).get("reason_code") or "").strip()
    return reason in _ENGINE_CONFIRMATION_REASONS


def _structured_engine_decision(
    orchestration_resolution: Optional[Mapping[str, Any]],
) -> Optional[str]:
    if not isinstance(orchestration_resolution, Mapping):
        return None
    for field in ("decision", "value"):
        normalized = _normalize_resolution_decision(orchestration_resolution.get(field))
        if normalized:
            return normalized
    return None


def _should_skip_collect_for_engine_resolution(
    *,
    active: Optional[Mapping[str, Any]],
    collect_key: str,
    awaiting: Optional[Mapping[str, Any]],
    orchestration_resolution: Optional[Mapping[str, Any]],
) -> bool:
    """True when the answer must resolve WorkflowEngine confirmation, not collect_input."""
    engine_decision = _structured_engine_decision(orchestration_resolution)
    # While clean is paused for confirmation, approve/modify/reject must never
    # be swallowed by a leftover contract collect key.
    if awaiting and engine_decision:
        step = str(awaiting.get("step_type") or "").strip().lower()
        if step == "clean":
            return True
    if _is_contract_collect_key(collect_key):
        return False
    if _is_engine_confirmation_decision(active, collect_key):
        return True
    if not awaiting:
        return False
    if not engine_decision:
        return False
    value = str(
        (orchestration_resolution or {}).get("value")
        or (orchestration_resolution or {}).get("decision")
        or ""
    ).strip().lower()
    return value in _ENGINE_RESOLUTION_VALUES


def _latest_user_message(messages: Optional[List[Mapping[str, Any]]], fallback: str = "") -> str:
    for msg in reversed(list(messages or [])):
        if str(msg.get("role")) == "user":
            return str(msg.get("content") or "").strip()
    return str(fallback or "").strip()


def _tool_summary(step: str, result: Optional[ToolResult]) -> Dict[str, Any]:
    if result is None:
        return {"step": step, "status": "unknown"}
    findings = []
    for item in list(result.findings or [])[:12]:
        if isinstance(item, dict):
            findings.append({
                "type": item.get("type"),
                "count": item.get("count"),
                "column": item.get("column"),
            })
    return {
        "step": step,
        "status": result.status,
        "summary": (result.summary or "")[:400],
        "findings": findings,
    }


def _leave_awaiting_answers(
    client: Any,
    *,
    session_id: str,
    user_id: str,
    session: Mapping[str, Any],
    status: str = "processing",
) -> Dict[str, Any]:
    """Exit orphaned awaiting_answers once execution resumes (no live question)."""
    current = dict(session)
    if str(current.get("status") or "") != "awaiting_answers":
        return current
    from datetime import datetime, timezone

    payload = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    client.table("data_setup_sessions").update(payload).eq(
        "id", session_id
    ).eq("user_id", user_id).execute()
    current["status"] = status
    return current


def _persist_tool_awaiting_ask(
    client: Any,
    *,
    session_id: str,
    user_id: str,
    session: Mapping[str, Any],
    step: str,
    tool_result: ToolResult,
) -> tuple[Dict[str, Any], AskUserDecision]:
    """Convert a tool-level awaiting_user result into a live active_decision."""
    meta = dict(getattr(tool_result, "metadata", None) or {})
    reason_code = str(
        meta.get("reason_code")
        or meta.get("reason")
        or "AWAITING_USER"
    )
    context = {
        "findings": list(tool_result.findings or [])[:8],
        **{k: v for k, v in meta.items() if k not in {"reason_code", "reason"}},
    }
    # Finalize often pauses for semantic mapping — use the mapping gate key.
    decision_key = "confirmation"
    if step == "finalize" or "semantic" in str(tool_result.summary or "").lower():
        decision_key = "mapping_confirmed"
        reason_code = reason_code if reason_code != "AWAITING_USER" else "AMBIGUOUS_MAPPING"
    ask = _ask_from_awaiting({
        "step_type": step,
        "reason_code": reason_code,
        "reason": tool_result.summary,
        "decision_key": decision_key,
        "context": context,
    })
    if decision_key == "mapping_confirmed":
        ask = _enrich_contract_ask(ask)
    progress = dict(session.get("processing_progress") or {})
    progress.update({
        "percent": 90 if step == "finalize" else 50,
        "stage": "awaiting_user",
        "step": step,
    })
    updated = persist_active_decision_and_stamps(
        client,
        session_id=session_id,
        user_id=user_id,
        session={
            **dict(session),
            "status": "awaiting_answers",
            "processing_progress": progress,
        },
        active_decision=_active_decision_payload_from_ask(
            ask,
            step_type=step,
            reason_code=reason_code,
            context=context,
        ),
        new_stamps=[],
    )
    return updated, ask


def _ask_from_awaiting(awaiting: Mapping[str, Any]) -> AskUserDecision:
    reason_code = str(
        awaiting.get("reason_code")
        or awaiting.get("reason")
        or "SEMANTIC_MEANING_REQUIRED"
    )
    template = template_for_reason_code(reason_code)
    if template:
        return coerce_ask_user(
            template["question"],
            reason=reason_code,
            context_key=template.get("context_key"),
            options=template.get("options"),
            decision_key=template.get("decision_key") or template.get("context_key"),
        )
    step = awaiting.get("step_type") or "step"
    return coerce_ask_user(
        f"ขั้นตอน {step} ต้องการคำยืนยันจากคุณก่อนดำเนินการต่อ ต้องการอนุมัติหรือไม่?",
        reason=reason_code,
        context_key="confirmation",
        decision_key=str(awaiting.get("decision_key") or "confirmation"),
        options=template_for_reason_code("AGGRESSIVE_CLEANING")["options"]
        if template_for_reason_code("AGGRESSIVE_CLEANING")
        else None,
    )


def _ask_from_unresolved(decision) -> AskUserDecision:
    options = []
    for opt in list(decision.options or []):
        if isinstance(opt, Mapping):
            options.append({
                "id": str(opt.get("id") or opt.get("value") or ""),
                "label": str(opt.get("label") or opt.get("id") or ""),
                "value": opt.get("value", opt.get("id")),
            })
    return coerce_ask_user(
        decision.question_th or decision.reason,
        reason=decision.reason,
        context_key=decision.decision_key,
        decision_key=decision.decision_key,
        expected_answer_type="option_or_text",
        options=options or None,
    )


def _enrich_contract_ask(decision: AskUserDecision) -> AskUserDecision:
    """Fill missing options / replace leaked approve-modify wording for contract keys."""
    key = str(decision.decision_key or decision.context_key or "").strip()
    if not _is_contract_collect_key(key):
        return decision
    th, _en, template_opts = _question_for(key, evidence={})
    opts = list(decision.options or [])
    question = str(decision.question or "").strip()
    leaked_ids = "approve" in question.lower() and "modify" in question.lower()
    option_ids = {
        str(
            getattr(opt, "id", None)
            or (opt.get("id") if isinstance(opt, Mapping) else "")
            or ""
        ).strip().lower()
        for opt in opts
    }
    engine_shaped = bool(option_ids & {"approve", "reject", "modify"})
    if not opts or leaked_ids or engine_shaped:
        return coerce_ask_user(
            th if (leaked_ids or engine_shaped or not question) else question,
            reason=decision.reason,
            context_key=decision.context_key or key,
            decision_key=key,
            options=template_opts,
            expected_answer_type="option_or_text",
        )
    return decision


def _ask_from_active_decision(active: Mapping[str, Any]) -> AskUserDecision:
    """Re-surface persisted backend truth without treating kickoff prose as an answer."""
    options = []
    for opt in list(active.get("options") or []):
        if not isinstance(opt, Mapping):
            continue
        option_id = str(opt.get("id") or opt.get("value") or "").strip()
        label = str(opt.get("label") or option_id).strip()
        if option_id and label:
            options.append({"id": option_id, "label": label, "value": opt.get("value", option_id)})
    key = str(active.get("decision_key") or "unknown")
    return coerce_ask_user(
        str(active.get("question") or "").strip(),
        reason=str(active.get("reason_code") or "active_decision_pending"),
        context_key=key,
        decision_key=key,
        expected_answer_type=str(active.get("expected_input") or "option_or_text"),
        options=options or None,
    )


def _active_decision_payload_from_ask(
    ask: AskUserDecision,
    *,
    options: Optional[list] = None,
    step_type: Optional[str] = None,
    reason_code: Optional[str] = None,
    context: Optional[Mapping[str, Any]] = None,
    free_text_allowed: Optional[bool] = None,
) -> Dict[str, Any]:
    opts = normalize_active_decision_options(options)
    if not opts and ask.options:
        opts = normalize_active_decision_options([
            opt.model_dump() if hasattr(opt, "model_dump") else opt
            for opt in (ask.options or [])
        ])
    reason = reason_code or ask.reason
    key = str(ask.decision_key or ask.context_key or "unknown")
    if free_text_allowed is None:
        free_text_allowed = not _is_engine_confirmation_decision(
            {"decision_key": key, "reason_code": reason},
            key,
        )
    # Never lock the UI: single-choice requires options.
    if not opts:
        free_text_allowed = True
    expected = None
    if opts and not free_text_allowed:
        expected = "single_choice"
    return build_active_decision_payload(
        decision_key=key,
        question=ask.question,
        options=opts,
        step_type=step_type,
        reason_code=reason,
        context=context,
        expected_input=expected,
        free_text_allowed=bool(free_text_allowed),
    )


def _try_unresolved_collect(
    session: Mapping[str, Any],
    *,
    required_for_capability: Optional[str] = "validate",
) -> Optional[tuple]:
    """Return (UnresolvedDecision, AskUserDecision) or None."""
    decisions = resolve_unresolved_decisions(
        session,
        required_for_capability=required_for_capability,
    )
    picked = select_one_decision(decisions)
    if picked is None:
        return None
    return picked, _ask_from_unresolved(picked)


def _session_has_original_prompt_capture(session: Mapping[str, Any]) -> bool:
    recipe = session.get("cleaning_recipe") or {}
    contract = recipe.get("data_contract") if isinstance(recipe, Mapping) else {}
    if not isinstance(contract, Mapping):
        return False
    return any(
        is_original_prompt_capture(session, decision_key, contract.get(field))
        for decision_key, field in (
            ("row_grain", "row_grain"),
            ("primary_metric", "metric_definition"),
            ("business_purpose", "business_purpose"),
            ("data_owner", "data_owner"),
        )
    )


def repair_missing_active_decision(
    client: Any,
    *,
    session_id: str,
    user_id: str,
    session: Mapping[str, Any],
    step_type: Optional[str] = None,
) -> tuple[Dict[str, Any], Optional[AskUserDecision]]:
    """Restore the question invariant for an awaiting setup session.

    A resolved answer retires ``active_decision`` before the controller plans the
    next action. If the per-turn action budget ends in that small window, older
    sessions can be left as ``awaiting_answers`` without anything the user can
    answer. Rebuild one deterministic unresolved question so resume is safe and
    idempotent; never invent a question when no backend blocker remains.
    """
    current = dict(session)
    if str(current.get("status") or "") != "awaiting_answers":
        return current, None

    progress = current.get("processing_progress") or {}
    raw_active = (
        progress.get("active_decision")
        if isinstance(progress, Mapping)
        else None
    )
    if isinstance(raw_active, Mapping):
        key = str(raw_active.get("decision_key") or "")
        question = str(raw_active.get("question") or "")
        opts = list(raw_active.get("options") or [])
        leaked = "approve" in question.lower() and "modify" in question.lower()
        pending = str(raw_active.get("status") or "pending") == "pending"
        if pending and _is_contract_collect_key(key) and (not opts or leaked):
            # Prompt-captured contract values are not trustworthy — fall through
            # so unresolved priority can replace this active question.
            if not _session_has_original_prompt_capture(current):
                enriched = _enrich_contract_ask(_ask_from_active_decision(raw_active))
                upgraded = _active_decision_payload_from_ask(
                    enriched,
                    options=[
                        opt.model_dump() if hasattr(opt, "model_dump") else dict(opt)
                        for opt in (enriched.options or [])
                    ],
                    step_type=raw_active.get("step_type"),
                    reason_code=raw_active.get("reason_code") or enriched.reason,
                    context=(
                        raw_active.get("context")
                        if isinstance(raw_active.get("context"), Mapping)
                        else None
                    ),
                    free_text_allowed=True,
                )
                updated = persist_active_decision_and_stamps(
                    client,
                    session_id=session_id,
                    user_id=user_id,
                    session=current,
                    active_decision=upgraded,
                    new_stamps=[],
                )
                return updated, enriched

        complete, _ = validate_active_decision_completeness(raw_active)
        if complete and pending:
            if _session_has_original_prompt_capture(current):
                # Re-evaluate priority below so a bogus captured metric cannot
                # leave a later owner question as the apparent live blocker.
                pass
            elif key == "data_owner" and not opts:
                upgraded = {
                    **dict(raw_active),
                    "options": [{
                        "id": "current_user",
                        "label": "ฉันเป็นเจ้าของข้อมูลชุดนี้",
                        "value": "current_user",
                    }],
                    "expected_input": "option_or_text",
                    "free_text_allowed": True,
                }
                updated = persist_active_decision_and_stamps(
                    client,
                    session_id=session_id,
                    user_id=user_id,
                    session=current,
                    active_decision=upgraded,
                    new_stamps=[],
                )
                return updated, _ask_from_active_decision(upgraded)
            else:
                return current, None

    collected = _try_unresolved_collect(current, required_for_capability=None)
    if collected is None:
        return current, None
    unresolved, ask = collected
    updated = persist_active_decision_and_stamps(
        client,
        session_id=session_id,
        user_id=user_id,
        session=current,
        active_decision=_active_decision_payload_from_ask(
            ask,
            options=unresolved.options,
            step_type=step_type or unresolved.required_for_capability,
            reason_code=unresolved.reason,
            context=unresolved.evidence,
        ),
        new_stamps=[],
    )
    return updated, ask


def _result_from_decision(
    decision,
    *,
    assistant_message: str,
    plan: Optional[Dict[str, Any]] = None,
    engine_result: Optional[Dict[str, Any]] = None,
    model_used: Optional[str] = None,
    audit: Optional[Dict[str, Any]] = None,
    llm_usage: Optional[Dict[str, Any]] = None,
    worklog_stamps: Optional[List[Dict[str, Any]]] = None,
    working_memory: Optional[Dict[str, Any]] = None,
) -> OrchestratorResult:
    options = None
    awaiting = None
    if isinstance(decision, AskUserDecision):
        options = [
            opt.model_dump() if hasattr(opt, "model_dump") else dict(opt)
            for opt in (decision.options or [])
        ] or None
        is_engine = _is_engine_confirmation_decision(
            {
                "decision_key": decision.decision_key,
                "reason_code": decision.reason,
            },
            str(decision.decision_key or decision.context_key or ""),
        )
        free_text_allowed = not is_engine
        if not options:
            free_text_allowed = True
        expected = decision.expected_answer_type
        if not expected:
            if options and not free_text_allowed:
                expected = "single_choice"
            elif options:
                expected = "option_or_text"
            else:
                expected = "free_text"
        awaiting = {
            "reason": decision.reason,
            "reason_code": decision.reason,
            "context_key": decision.context_key,
            "decision_key": decision.decision_key,
            "question": decision.question,
            "options": options,
            "expected_input": expected,
            "free_text_allowed": free_text_allowed,
            "step_type": None,
        }
        safe = strip_raw_validator_checklist(assistant_message)
        if not safe:
            assistant_message = decision.question
        else:
            assistant_message = safe
    audit_out = dict(audit or {})
    if llm_usage is not None:
        audit_out["llm_usage"] = llm_usage
    return OrchestratorResult(
        decision=decision,
        assistant_message=assistant_message,
        workflow_plan=plan,
        engine_result=engine_result,
        awaiting_user=awaiting,
        options=options,
        model_used=model_used,
        prompt_version=MATAQOR_ORCHESTRATOR_PROMPT_VERSION,
        audit=audit_out,
        llm_usage=llm_usage,
        worklog_stamps=list(worklog_stamps or []),
        working_memory=working_memory,
    )


class WorkflowOrchestrator:
    """Conversational orchestrator bound to a WorkflowEngine instance."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        llm: LlmClient | None = None,
        engine: WorkflowEngine | None = None,
    ):
        self.client = client or get_supabase_client()
        self.llm = llm or LlmClient()
        self.engine = engine or WorkflowEngine(client=self.client)

    def _load_session(self, session_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        response = (
            self.client.table("data_setup_sessions")
            .select("*")
            .eq("id", session_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def _resolve_model(self, tier: str = "free") -> str:
        if settings.LLM_MODEL_ORCHESTRATOR:
            return settings.LLM_MODEL_ORCHESTRATOR
        if (tier or "").lower() in {"plus", "pro"}:
            return settings.LLM_MODEL_LIGHT or settings.LLM_MODEL_PREMIUM
        return settings.LLM_MODEL_LIGHT or settings.LLM_MODEL_FREE

    async def _llm_decide(
        self,
        *,
        context: Mapping[str, Any],
        user_message: str,
        tier: str,
        session_id: str = "unknown",
        working_memory: Optional[Mapping[str, Any]] = None,
        locale: str = "th",
    ) -> tuple[Any, Optional[str], List[Dict[str, Any]]]:
        model = self._resolve_model(tier)
        usage_calls: List[Dict[str, Any]] = []
        messages = [
            {
                "role": "system",
                "content": (
                    SYSTEM_PROMPT
                    + "\nThe selected UI language is "
                    + ("English" if locale == "en" else "Thai")
                    + ". Write every user-facing question, option label, reason, and response in that language."
                ),
            },
            {
                "role": "user",
                "content": build_user_prompt(
                    workflow_context=context.get("workflow") or {},
                    user_message=user_message,
                    source_summary=context.get("source_summary"),
                    recent_turns=context.get("recent_turns"),
                    last_tool_summary=context.get("last_tool_summary"),
                    working_memory=working_memory,
                ),
            },
        ]
        try:
            response, calls = await self.llm.safe_chat_completion_with_usage(
                model=model,
                messages=messages,
                temperature=0.1,
                max_tokens=700,
                kind="decision",
            )
            usage_calls.extend(calls)
            content = response.choices[0].message.content or ""
            used = getattr(response, "model", None) or model
            try:
                return parse_orchestrator_decision(content), used, usage_calls
            except DecisionParseError:
                # One repair attempt — both original + repair usage are counted.
                repair_messages = messages + [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            "Your previous output was invalid. "
                            "Reply with one valid JSON decision object only."
                        ),
                    },
                ]
                repair, repair_calls = await self.llm.safe_chat_completion_with_usage(
                    model=model,
                    messages=repair_messages,
                    temperature=0.0,
                    max_tokens=500,
                    kind="repair",
                )
                usage_calls.extend(repair_calls)
                repair_content = repair.choices[0].message.content or ""
                used = getattr(repair, "model", None) or used
                return parse_orchestrator_decision(repair_content), used, usage_calls
        except Exception as exc:
            logger.warning(
                "orchestrator_llm_failed",
                extra={"error": str(exc)[:200]},
            )
            emit_workflow_event(
                ORCHESTRATOR_LLM_FAILED,
                session_id=session_id,
                reason_code=type(exc).__name__,
                metadata={"error": str(exc)[:200]},
            )
            return None, model, usage_calls

    def _deterministic_fallback(
        self,
        *,
        workflow_ctx: Mapping[str, Any],
        last_tool_summary: Optional[Mapping[str, Any]] = None,
    ):
        awaiting = workflow_ctx.get("awaiting_user")
        if awaiting:
            return _ask_from_awaiting(awaiting)
        next_action = workflow_ctx.get("next_action") or {}
        action = next_action.get("action")
        step = next_action.get("step_type")
        if action in {"execute", "retry"} and step:
            return coerce_tool_call(step, reason=str(next_action.get("reason") or ""))
        if action == "complete" or workflow_ctx.get("status") == "ready":
            return coerce_respond(
                "การเตรียมข้อมูลเสร็จแล้ว และพร้อมสำหรับการวิเคราะห์"
            )
        if last_tool_summary and last_tool_summary.get("status") == "failed":
            return coerce_respond(
                f"ขั้นตอน {last_tool_summary.get('step')} ล้มเหลว: "
                f"{last_tool_summary.get('summary') or 'unknown error'}"
            )
        if action == "blocked":
            return coerce_respond(
                f"ยังดำเนินการต่อไม่ได้: {next_action.get('reason') or 'blocked'}"
            )
        return coerce_respond(
            "ระบบเตรียมข้อมูลพร้อมช่วยต่อเมื่อคุณพร้อม "
            "บอกได้เลยว่าต้องการตรวจ Mapping, Cleaning หรือสรุปสถานะปัจจุบัน"
        )

    @staticmethod
    def _plan_has_executable_next(workflow_ctx: Mapping[str, Any]) -> bool:
        next_action = workflow_ctx.get("next_action") or {}
        return (
            str(next_action.get("action") or "") in {"execute", "retry"}
            and bool(next_action.get("step_type"))
            and not workflow_ctx.get("awaiting_user")
        )

    def _deterministic_next_decision(
        self,
        *,
        workflow_ctx: Mapping[str, Any],
        last_tool_summary: Optional[Mapping[str, Any]] = None,
        allow_after_tool: bool = False,
    ):
        """Skip LLM when WorkflowPlan already indicates the next safe capability."""
        if workflow_ctx.get("awaiting_user"):
            return None
        next_action = workflow_ctx.get("next_action") or {}
        action = str(next_action.get("action") or "")
        step = str(next_action.get("step_type") or "").strip()
        if action in {"execute", "retry"} and step:
            if allow_after_tool or not last_tool_summary:
                return coerce_tool_call(
                    step,
                    reason=str(next_action.get("reason") or "deterministic_continuation"),
                )
        if action == "complete" or workflow_ctx.get("status") == "ready":
            return coerce_respond(
                "การเตรียมข้อมูลเสร็จแล้ว และพร้อมสำหรับการวิเคราะห์"
            )
        return None

    async def handle_message(
        self,
        *,
        session_id: str,
        user_id: str,
        message: str = "",
        messages: Optional[List[Mapping[str, Any]]] = None,
        tier: str = "free",
        locale: str = "th",
        llm_decision_override: Any = None,
        orchestration_resolution: Optional[Mapping[str, Any]] = None,
        setup_intent: Optional[str] = None,
        settlement_key: Optional[str] = None,
    ) -> OrchestratorResult:
        usage_calls: List[Dict[str, Any]] = []
        turn_stamps: List[Dict[str, Any]] = []
        last_memory_prompt: Optional[Dict[str, Any]] = None
        # `_finish` is also used by the missing-session and already-ready early
        # returns, so the timer must exist before either branch can run.
        turn_timer = ControllerTurnTimer(session_id=session_id, user_id=user_id)

        async def _finish(result: OrchestratorResult, *, stop_reason: str = "completed") -> OrchestratorResult:
            perf = turn_timer.summary(stop_reason=stop_reason)
            summary = summarize_calls(usage_calls)
            result.llm_usage = summary
            result.audit = {
                **dict(result.audit or {}),
                "llm_usage": summary,
                "performance": perf,
                "stop_reason": stop_reason,
            }
            if turn_stamps:
                existing = list(result.worklog_stamps or [])
                seen = {s.get("stamp_id") for s in existing}
                for stamp in turn_stamps:
                    if stamp.get("stamp_id") not in seen:
                        existing.append(stamp)
                result.worklog_stamps = existing
            if last_memory_prompt and not result.working_memory:
                result.working_memory = last_memory_prompt
            settled = await settle_orchestrator_usage(
                user_id=user_id,
                session_id=session_id,
                calls=usage_calls,
                settlement_key=settlement_key,
                decision_type=getattr(result.decision, "type", None),
                prompt_version=result.prompt_version,
                client=self.client,
            )
            result.audit["usage_settlement"] = {
                "settled": settled.get("settled"),
                "idempotent_skip": settled.get("idempotent_skip"),
            }
            return result

        session = self._load_session(session_id, user_id)
        if not session:
            decision = coerce_respond("ไม่พบ Data Setup session สำหรับคำขอนี้")
            return await _finish(
                _result_from_decision(decision, assistant_message=decision.message)
            )

        if session.get("status") == "ready":
            decision = coerce_respond(
                "Dataset Version พร้อมวิเคราะห์แล้ว สามารถถามคำถามเชิงวิเคราะห์ได้เลย"
            )
            plan = await asyncio.to_thread(
                self.engine.get_workflow_plan, session_id, session=session, user_id=user_id
            )
            plan_dict = plan if isinstance(plan, dict) else dict(plan or {})
            memory = build_working_memory(
                session=session,
                workflow_plan=plan_dict,
                user_question=message or _latest_user_message(messages),
                user_tier=tier,
                include_contract_decisions=False,
            )
            last_memory_prompt = memory_for_prompt(memory)
            return await _finish(
                _result_from_decision(
                    decision,
                    assistant_message=decision.message,
                    plan=plan_dict,
                    working_memory=last_memory_prompt,
                )
            )

        user_message = message or _latest_user_message(messages)
        initial_setup_request = bool(
            setup_intent == "prepare_attached_source_for_analysis"
            and not orchestration_resolution
        )
        if not user_message and setup_intent:
            # Attachment-only entry: internal intent, not fake visible chat copy.
            if setup_intent == "continue_workflow":
                user_message = ""
            elif setup_intent == "prepare_attached_source_for_analysis":
                user_message = "เตรียมแหล่งข้อมูลที่แนบมาสำหรับการวิเคราะห์"
            else:
                user_message = str(setup_intent)
        max_actions = max(
            1,
            int(
                getattr(settings, "MAX_CONTROLLER_ACTIONS_PER_USER_TURN", None)
                or settings.MAX_ORCHESTRATOR_ACTIONS
                or 3
            ),
        )
        last_tool_summary: Optional[Dict[str, Any]] = None
        seen_requests: List[str] = []
        model_used: Optional[str] = None
        audit: Dict[str, Any] = {
            "session_id": session_id,
            "user_id": user_id,
            "prompt_version": MATAQOR_ORCHESTRATOR_PROMPT_VERSION,
            "actions": [],
            "setup_intent": setup_intent,
            "controller": "toolbox_v1",
        }

        for iteration in range(max_actions):
            turn_timer.start_iteration(iteration + 1)
            with turn_timer.track("state_load_ms"):
                context = await asyncio.to_thread(
                    build_orchestrator_llm_context,
                    engine=self.engine,
                    session_id=session_id,
                    session=session,
                    user_id=user_id,
                    messages=messages,
                    last_tool_summary=last_tool_summary,
                )
            workflow_ctx = context.get("workflow") or {}
            plan_obj = context.get("plan")
            if hasattr(plan_obj, "model_dump"):
                plan_dict = plan_obj.model_dump()
            elif isinstance(plan_obj, dict):
                plan_dict = plan_obj
            else:
                plan_dict = dict(plan_obj or {})
            with turn_timer.track("memory_ms"):
                memory = build_working_memory(
                    session=session,
                    workflow_plan=plan_dict,
                    source_summary=context.get("source_summary"),
                    last_tool_summary=last_tool_summary,
                    user_question=user_message,
                    user_tier=tier,
                )
            last_memory_prompt = memory_for_prompt(memory)

            # Structured retry from UI (Phase 6) — engine still validates.
            if (
                orchestration_resolution
                and str(orchestration_resolution.get("action") or "").lower() == "retry"
            ):
                step = str(
                    orchestration_resolution.get("step_type")
                    or orchestration_resolution.get("step")
                    or ""
                ).strip()
                orchestration_resolution = None
                if step:
                    llm_decision_override = coerce_tool_call(
                        step, reason="ui_retry"
                    )
                    user_message = user_message or "ลองใหม่"

            # Phase 7.2: apply active collect_input answer (decision_key-aware).
            active = memory.active_decision
            if initial_setup_request and active:
                ask = _ask_from_active_decision(active)
                audit["actions"].append({
                    "decision_type": "ask_user",
                    "decision_key": ask.decision_key,
                    "reason": "initial_prompt_not_consumed_as_answer",
                })
                return await _finish(_result_from_decision(
                    ask,
                    assistant_message=ask.question,
                    plan=plan_dict,
                    model_used=model_used or "controller_deterministic",
                    audit=audit,
                    worklog_stamps=turn_stamps,
                    working_memory=last_memory_prompt,
                ), stop_reason="awaiting_user")
            decision_key_from_ui = None
            if isinstance(orchestration_resolution, Mapping):
                decision_key_from_ui = orchestration_resolution.get("decision_key")
            collect_key = str(
                (active or {}).get("decision_key")
                or decision_key_from_ui
                or ""
            ).strip()
            collect_applied = False
            awaiting = workflow_ctx.get("awaiting_user")
            if collect_key and user_message and not initial_setup_request:
                if _should_skip_collect_for_engine_resolution(
                    active=active if isinstance(active, Mapping) else None,
                    collect_key=collect_key,
                    awaiting=awaiting if isinstance(awaiting, Mapping) else None,
                    orchestration_resolution=(
                        orchestration_resolution
                        if isinstance(orchestration_resolution, Mapping)
                        else None
                    ),
                ):
                    # Engine confirmation — fall through to resolve_awaiting_user.
                    pass
                elif is_decision_confirmed(session, collect_key):
                    user_message = ""
                    orchestration_resolution = None
                else:
                    opts = list((active or {}).get("options") or [])
                    if orchestration_resolution and orchestration_resolution.get("value") is not None:
                        answer_text = str(orchestration_resolution.get("value"))
                    else:
                        answer_text = user_message
                    value, updates = parse_simple_answer(
                        answer_text, decision_key=collect_key, options=opts
                    )
                    if updates:
                        session, stamp = apply_decision_answer(
                            self.client,
                            session_id=session_id,
                            user_id=user_id,
                            session=session,
                            decision_key=collect_key,
                            context_updates=updates,
                            value=value,
                        )
                        if stamp is not None:
                            turn_stamps.append(stamp_to_dict(stamp))
                        audit["actions"].append({
                            "decision_type": "collect_input_applied",
                            "decision_key": collect_key,
                        })
                        with turn_timer.track("state_load_ms"):
                            session = self._load_session(session_id, user_id) or session
                        # If validate/map left an engine pause open, clear it when
                        # the readiness gate was confirmed True so the step can resume.
                        confirmed_true = (
                            collect_key in {"mapping_confirmed", "business_context_reviewed"}
                            and (
                                updates.get(collect_key) is True
                                or value is True
                                or str(value).strip().lower() in {"true", "1", "yes", "approve", "approved"}
                            )
                        )
                        if confirmed_true and awaiting:
                            step = str(awaiting.get("step_type") or "")
                            if step:
                                try:
                                    await asyncio.to_thread(
                                        self.engine.resolve_awaiting_user,
                                        session_id,
                                        step,
                                        user_id=user_id,
                                        resolution={"decision": "approved"},
                                        reason=f"User confirmed {collect_key}",
                                    )
                                    audit["actions"].append({
                                        "decision_type": "engine_pause_cleared",
                                        "decision_key": collect_key,
                                        "step_type": step,
                                    })
                                except Exception as exc:
                                    logger.warning(
                                        "orchestrator_clear_awaiting_failed",
                                        extra={"step": step, "error": str(exc)[:200]},
                                    )
                        user_message = ""
                        orchestration_resolution = None
                        collect_applied = True
                        continue

            # Prefer resolving awaiting_user from structured UI resolution or text.
            if (
                awaiting
                and (user_message or orchestration_resolution)
                and not collect_applied
                and not initial_setup_request
            ):
                if orchestration_resolution and (
                    orchestration_resolution.get("decision") is not None
                    or _structured_engine_decision(orchestration_resolution)
                ):
                    decision_value = _structured_engine_decision(orchestration_resolution)
                    if decision_value is None:
                        decision_value = _normalize_resolution_decision(
                            orchestration_resolution.get("decision")
                        )
                    if decision_value not in {
                        "approved", "rejected", "modified", "ambiguous"
                    }:
                        proposal = UserResolutionProposal(
                            decision="ambiguous", note="invalid_structured_decision"
                        )
                    else:
                        proposal = UserResolutionProposal(
                            decision=decision_value,  # type: ignore[arg-type]
                            context_updates=dict(
                                orchestration_resolution.get("context_updates") or {}
                            ),
                            note="structured_ui",
                        )
                    orchestration_resolution = None
                else:
                    proposal = parse_user_resolution(user_message, awaiting=awaiting)
                handled = await self._handle_resolution(
                    session_id=session_id,
                    user_id=user_id,
                    session=session,
                    proposal=proposal,
                    awaiting=awaiting,
                    plan=plan_dict,
                    audit=audit,
                )
                if handled is not None:
                    if handled.get("continue"):
                        session = handled["session"]
                        user_message = ""  # avoid re-parsing same message
                        last_tool_summary = handled.get("last_tool_summary")
                        continue
                    return await _finish(handled["result"])

            # Phase 7.2: ONE unresolved decision — never dump contract checklists.
            next_action = plan_dict.get("next_action") or {}
            next_step = str(next_action.get("step_type") or "").strip().lower()
            next_act = str(next_action.get("action") or "").strip().lower()
            unresolved = next_unresolved(memory)
            validate_blocked = (
                (last_tool_summary or {}).get("step") == "validate"
                and (last_tool_summary or {}).get("status") in {"awaiting_user", "failed"}
            )
            # Contract questions must not preempt Engine-approved execution or the
            # immediate post-tool narration turn (e.g. after clean completes).
            just_finished_tool = bool(
                last_tool_summary
                and last_tool_summary.get("status") == "completed"
            )
            should_collect = bool(unresolved) and not awaiting and (
                validate_blocked
                or (next_step in {"validate", "finalize"} and not just_finished_tool)
            )
            if (
                should_collect
                and llm_decision_override is None
                and int(getattr(settings, "MAX_SETUP_QUESTIONS_PER_TURN", 1) or 1) >= 1
            ):
                ask = _ask_from_unresolved(unresolved)
                session = persist_active_decision_and_stamps(
                    self.client,
                    session_id=session_id,
                    user_id=user_id,
                    session=session,
                    active_decision=_active_decision_payload_from_ask(
                        ask,
                        options=unresolved.options,
                        step_type=next_step or None,
                        reason_code=unresolved.reason,
                        context=unresolved.evidence,
                    ),
                    new_stamps=[],
                )
                model_used = model_used or "controller_deterministic"
                return await _finish(_result_from_decision(
                    ask,
                    assistant_message=ask.question,
                    plan=plan_dict,
                    engine_result=last_tool_summary,
                    model_used=model_used,
                    audit=audit,
                    worklog_stamps=turn_stamps,
                    working_memory=last_memory_prompt,
                ))

            if llm_decision_override is not None:
                raw_decision = llm_decision_override
                llm_decision_override = None  # one-shot
                model_used = model_used or "override"
            else:
                det = None
                # Prefer the WorkflowPlan whenever the next step is runnable —
                # including continue_workflow with no prior tool summary (do not
                # wait for the LLM to rediscover finalize/retry).
                if (
                    self._plan_has_executable_next(workflow_ctx)
                    or (
                        last_tool_summary
                        and last_tool_summary.get("status") == "completed"
                    )
                    or str((workflow_ctx.get("next_action") or {}).get("action") or "")
                    == "complete"
                    or workflow_ctx.get("status") == "ready"
                ):
                    det = self._deterministic_next_decision(
                        workflow_ctx=workflow_ctx,
                        last_tool_summary=last_tool_summary,
                        allow_after_tool=True,
                    )
                if det is not None:
                    raw_decision = det
                    model_used = model_used or "controller_deterministic"
                else:
                    with turn_timer.track("llm_ms"):
                        raw_decision, model_used, call_usage = await self._llm_decide(
                            context=context,
                            user_message=user_message
                            or (
                                "Inspect working memory and choose the one required capability or question."
                                if locale == "en"
                                else "สังเกต working memory แล้วเลือก capability หรือคำถามเดียวที่จำเป็น"
                            ),
                            tier=tier,
                            session_id=session_id,
                            working_memory=last_memory_prompt,
                            locale=locale,
                        )
                    turn_timer.note_llm_call()
                    usage_calls.extend(call_usage)
                if raw_decision is None:
                    emit_workflow_event(
                        ORCHESTRATOR_FALLBACK,
                        session_id=session_id,
                        reason_code="llm_unavailable",
                        source_type=str(session.get("source_type") or "") or None,
                    )
                    raw_decision = self._deterministic_fallback(
                        workflow_ctx=workflow_ctx,
                        last_tool_summary=last_tool_summary,
                    )

            try:
                decision = validate_decision(raw_decision, session=session)
            except DecisionValidationError as exc:
                logger.info(
                    "orchestrator_decision_rejected",
                    extra={"code": exc.code, "detail": str(exc)[:200]},
                )
                emit_workflow_event(
                    ORCHESTRATOR_MALFORMED,
                    session_id=session_id,
                    reason_code=str(exc.code or "invalid_decision"),
                    metadata={"detail": str(exc)[:200]},
                )
                emit_workflow_event(
                    ORCHESTRATOR_FALLBACK,
                    session_id=session_id,
                    reason_code="malformed_decision",
                )
                decision = self._deterministic_fallback(
                    workflow_ctx=workflow_ctx,
                    last_tool_summary=last_tool_summary,
                )
                decision = validate_decision(decision, session=session)

            audit["actions"].append({
                "decision_type": getattr(decision, "type", None),
                "step_type": getattr(decision, "step_type", None),
                "reason": getattr(decision, "reason", None),
            })
            emit_workflow_event(
                ORCHESTRATOR_DECISION,
                session_id=session_id,
                step_type=getattr(decision, "step_type", None),
                decision_type=getattr(decision, "type", None),
                source_type=str(session.get("source_type") or "") or None,
            )

            if isinstance(decision, AskUserDecision):
                # Replace leaked multi-field validator checklists with ONE decision.
                if not strip_raw_validator_checklist(decision.question) and unresolved:
                    decision = _ask_from_unresolved(unresolved)
                elif not decision.decision_key and unresolved:
                    decision = AskUserDecision(
                        question=decision.question,
                        reason=decision.reason,
                        context_key=decision.context_key or unresolved.decision_key,
                        decision_key=unresolved.decision_key,
                        options=decision.options,
                    )
                decision = _enrich_contract_ask(decision)
                session = persist_active_decision_and_stamps(
                    self.client,
                    session_id=session_id,
                    user_id=user_id,
                    session=session,
                    active_decision=_active_decision_payload_from_ask(
                        decision,
                        step_type=next_step or None,
                        reason_code=getattr(decision, "reason", None),
                    ),
                    new_stamps=[],
                )
                emit_workflow_event(
                    STEP_AWAITING_USER,
                    session_id=session_id,
                    step_type=getattr(decision, "step_type", None),
                    status="awaiting_user",
                    reason_code=getattr(decision, "reason", None),
                )
                turn_timer.finish_iteration(
                    decision_type="ask_user",
                    capability=getattr(decision, "decision_key", None),
                )
                return await _finish(_result_from_decision(
                    decision,
                    assistant_message=decision.question,
                    plan=plan_dict,
                    model_used=model_used,
                    audit=audit,
                    worklog_stamps=turn_stamps,
                    working_memory=last_memory_prompt,
                ), stop_reason="awaiting_user")

            if isinstance(decision, RespondDecision):
                # Ground success claims in backend state when a tool summary exists.
                message_out = decision.message
                if last_tool_summary and last_tool_summary.get("status") == "failed":
                    if any(
                        token in message_out.lower()
                        for token in ("completed", "สำเร็จ", "เสร็จ", "done")
                    ):
                        message_out = (
                            f"ขั้นตอน {last_tool_summary.get('step')} ล้มเหลว: "
                            f"{last_tool_summary.get('summary')}"
                        )
                if (
                    last_tool_summary
                    and last_tool_summary.get("status") == "completed"
                    and self._plan_has_executable_next(workflow_ctx)
                ):
                    turn_timer.finish_iteration(decision_type="continue", capability=None)
                    user_message = ""
                    continue
                turn_timer.finish_iteration(decision_type="respond", capability=None)
                return await _finish(_result_from_decision(
                    RespondDecision(message=message_out),
                    assistant_message=message_out,
                    plan=plan_dict,
                    engine_result=last_tool_summary,
                    model_used=model_used,
                    audit=audit,
                ), stop_reason="respond")

            if isinstance(decision, ToolCallDecision):
                step = decision.step_type
                signature = f"tool:{step}"
                if seen_requests.count(signature) >= 2:
                    msg = (
                        f"ระบบหยุดการวนซ้ำที่ขั้นตอน {step} "
                        "เพราะผลลัพธ์ไม่คืบหน้า กรุณาตรวจสอบการตั้งค่าหรือตอบคำถามที่ยค้าง"
                    )
                    return await _finish(_result_from_decision(
                        coerce_respond(msg),
                        assistant_message=msg,
                        plan=plan_dict,
                        model_used=model_used,
                        audit=audit,
                    ), stop_reason="blocked")
                seen_requests.append(signature)

                # Apply only allowlisted proposed_input keys before engine execute.
                proposed = dict(decision.proposed_input or {})
                safe_updates = {
                    key: proposed[key]
                    for key in _SAFE_PROPOSED_INPUT_KEYS
                    if key in proposed and proposed[key] is not None
                }
                if safe_updates:
                    try:
                        session = await asyncio.to_thread(
                            apply_context_updates,
                            self.client,
                            session_id=session_id,
                            user_id=user_id,
                            session=session,
                            context_updates=safe_updates,
                        )
                        audit["actions"].append({
                            "decision_type": "proposed_input_applied",
                            "keys": sorted(safe_updates.keys()),
                        })
                    except Exception as exc:
                        msg = f"ไม่สามารถใช้ proposed_input ได้: {exc}"
                        return await _finish(_result_from_decision(
                            coerce_respond(msg),
                            assistant_message=msg,
                            plan=plan_dict,
                            model_used=model_used,
                            audit=audit,
                        ), stop_reason="blocked")

                try:
                    session = _leave_awaiting_answers(
                        self.client,
                        session_id=session_id,
                        user_id=user_id,
                        session=session,
                    )
                    with turn_timer.track("tool_ms"):
                        tool_result = await asyncio.to_thread(
                            self.engine.execute_step,
                            session_id,
                            step,
                            user_id=user_id,
                            session=session,
                        )
                except ConfirmationRequired as exc:
                    step = exc.decision.step_type
                    reason_code = str(
                        (exc.decision.metadata or {}).get("reason_code")
                        or exc.decision.reason
                        or ""
                    )
                    # Deterministic setup tools: map blockers to ONE unresolved decision,
                    # not generic "approve validate" prompts.
                    if step in {"validate", "map", "prepare", "inspect"}:
                        collected = _try_unresolved_collect(session)
                        if collected is not None:
                            unresolved_item, ask = collected
                            progress = dict(session.get("processing_progress") or {})
                            progress.update({
                                "percent": 50,
                                "stage": "awaiting_user",
                                "step": step,
                            })
                            session = persist_active_decision_and_stamps(
                                self.client,
                                session_id=session_id,
                                user_id=user_id,
                                session={
                                    **dict(session),
                                    "status": "awaiting_answers",
                                    "processing_progress": progress,
                                },
                                active_decision=_active_decision_payload_from_ask(
                                    ask,
                                    options=unresolved_item.options,
                                    step_type=step,
                                    reason_code=unresolved_item.reason,
                                    context=unresolved_item.evidence,
                                ),
                                new_stamps=[],
                            )
                            plan = await asyncio.to_thread(
                                self.engine.get_workflow_plan,
                                session_id,
                                session=session,
                                user_id=user_id,
                            )
                            return await _finish(_result_from_decision(
                                ask,
                                assistant_message=ask.question,
                                plan=plan,
                                engine_result={"action": "awaiting_user", "step": step},
                                model_used=model_used,
                                audit=audit,
                            ), stop_reason="awaiting_user")
                    ask = _ask_from_awaiting({
                        "step_type": exc.decision.step_type,
                        "reason_code": reason_code,
                        "reason": exc.decision.reason,
                        "context": (exc.decision.metadata or {}).get("context") or {},
                    })
                    progress = dict(session.get("processing_progress") or {})
                    progress.update({
                        "percent": 50,
                        "stage": "awaiting_user",
                        "step": exc.decision.step_type,
                    })
                    session = persist_active_decision_and_stamps(
                        self.client,
                        session_id=session_id,
                        user_id=user_id,
                        session={
                            **dict(session),
                            "status": "awaiting_answers",
                            "processing_progress": progress,
                        },
                        active_decision=_active_decision_payload_from_ask(
                            ask,
                            step_type=exc.decision.step_type,
                            reason_code=reason_code,
                            context=(exc.decision.metadata or {}).get("context") or {},
                        ),
                        new_stamps=[],
                    )
                    plan = await asyncio.to_thread(
                        self.engine.get_workflow_plan,
                        session_id,
                        session=session,
                        user_id=user_id,
                    )
                    return await _finish(_result_from_decision(
                        ask,
                        assistant_message=ask.question,
                        plan=plan,
                        engine_result={"action": "awaiting_user", "step": step},
                        model_used=model_used,
                        audit=audit,
                    ), stop_reason="awaiting_user")
                except Exception as exc:
                    logger.warning(
                        "orchestrator_tool_failed",
                        extra={
                            "session_id": session_id,
                            "step_type": step,
                            "error": str(exc)[:200],
                        },
                    )
                    err_text = str(exc)
                    reason_code = "TOOL_FAILED"
                    for code in (
                        "DEPENDENCY_NOT_SATISFIED",
                        "STALE_DEPENDENCY",
                        "CONFIRMATION_REQUIRED",
                        "ARTIFACT_MISSING",
                        "STEP_NOT_RETRYABLE",
                    ):
                        if code in err_text:
                            reason_code = code
                            break
                    emit_workflow_event(
                        ORCHESTRATOR_ENGINE_REJECTION,
                        session_id=session_id,
                        step_type=step,
                        reason_code=reason_code,
                        metadata={"error": err_text[:200]},
                    )
                    msg = f"ไม่สามารถรันขั้นตอน {step} ได้: {str(exc)[:240]}"
                    plan = await asyncio.to_thread(
                        self.engine.get_workflow_plan,
                        session_id,
                        session=session,
                        user_id=user_id,
                    )
                    return await _finish(_result_from_decision(
                        coerce_respond(msg),
                        assistant_message=msg,
                        plan=plan,
                        engine_result={"step": step, "status": "failed", "summary": str(exc)[:240]},
                        model_used=model_used,
                        audit=audit,
                    ))

                last_tool_summary = _tool_summary(step, tool_result)
                # Enrich summary with metadata for stamps (safe fields only).
                if isinstance(getattr(tool_result, "metadata", None), dict):
                    last_tool_summary["metadata"] = {
                        k: v for k, v in tool_result.metadata.items()
                        if isinstance(v, (str, int, float, bool)) or v is None
                    }
                stamp = build_tool_stamp(
                    session_id=session_id,
                    step=step,
                    tool_summary=last_tool_summary,
                )
                if stamp is not None:
                    turn_stamps.append(stamp_to_dict(stamp))
                    with turn_timer.track("stamp_persist_ms"):
                        session = persist_stamps_only(
                            self.client,
                            session_id=session_id,
                            user_id=user_id,
                            session=session,
                            new_stamps=[stamp],
                        )
                with turn_timer.track("db_ms"):
                    session = self._load_session(session_id, user_id) or session
                # After tool success, continue run_until_pause loop.
                if tool_result.status == "failed":
                    msg = f"ขั้นตอน {step} ล้มเหลว: {tool_result.summary}"
                    turn_timer.finish_iteration(decision_type="tool_call", capability=step)
                    return await _finish(_result_from_decision(
                        coerce_respond(msg),
                        assistant_message=msg,
                        plan=plan_dict,
                        engine_result=last_tool_summary,
                        model_used=model_used,
                        audit=audit,
                    ), stop_reason="failed")
                if tool_result.status == "awaiting_user":
                    session, ask = _persist_tool_awaiting_ask(
                        self.client,
                        session_id=session_id,
                        user_id=user_id,
                        session=session,
                        step=step,
                        tool_result=tool_result,
                    )
                    plan = await asyncio.to_thread(
                        self.engine.get_workflow_plan,
                        session_id,
                        session=session,
                        user_id=user_id,
                    )
                    turn_timer.finish_iteration(decision_type="tool_call", capability=step)
                    return await _finish(_result_from_decision(
                        ask,
                        assistant_message=ask.question,
                        plan=plan,
                        engine_result=last_tool_summary,
                        model_used=model_used,
                        audit=audit,
                        worklog_stamps=turn_stamps,
                    ), stop_reason="awaiting_user")
                if str(session.get("status") or "") == "ready":
                    emit_workflow_event(
                        WORKFLOW_READY,
                        session_id=session_id,
                        step_type="finalize",
                        status="ready",
                        source_type=str(session.get("source_type") or "") or None,
                    )
                    turn_timer.finish_iteration(decision_type="tool_call", capability=step)
                    return await _finish(_result_from_decision(
                        coerce_respond(
                            "การเตรียมข้อมูลเสร็จแล้ว และพร้อมสำหรับการวิเคราะห์"
                        ),
                        assistant_message=(
                            "การเตรียมข้อมูลเสร็จแล้ว และพร้อมสำหรับการวิเคราะห์"
                        ),
                        plan=plan_dict,
                        engine_result=last_tool_summary,
                        model_used=model_used,
                        audit=audit,
                        worklog_stamps=turn_stamps,
                    ), stop_reason="ready")
                if step == "finalize":
                    # Finalize ran but session is not ready — surface it; do not
                    # silently continue as if the setup loop should invent work.
                    msg = (
                        f"ขั้นตอน finalize ยังไม่พร้อม: "
                        f"{tool_result.summary or session.get('status') or 'unknown'}"
                    )
                    turn_timer.finish_iteration(decision_type="tool_call", capability=step)
                    return await _finish(_result_from_decision(
                        coerce_respond(msg),
                        assistant_message=msg,
                        plan=plan_dict,
                        engine_result=last_tool_summary,
                        model_used=model_used,
                        audit=audit,
                        worklog_stamps=turn_stamps,
                    ), stop_reason="blocked")
                turn_timer.finish_iteration(decision_type="tool_call", capability=step)
                user_message = ""
                continue

        with turn_timer.track("db_ms"):
            plan = await asyncio.to_thread(
                self.engine.get_workflow_plan, session_id, session=session, user_id=user_id
            )
        plan_dict = plan if isinstance(plan, dict) else dict(plan or {})
        next_action = plan_dict.get("next_action") or {}
        session, repaired_ask = repair_missing_active_decision(
            self.client,
            session_id=session_id,
            user_id=user_id,
            session=session,
            step_type=str(next_action.get("step_type") or "") or None,
        )
        if repaired_ask is not None:
            audit["continuation_available"] = False
            audit["actions"].append({
                "decision_type": "ask_user",
                "decision_key": repaired_ask.decision_key,
                "reason": "repaired_missing_active_decision",
            })
            return await _finish(_result_from_decision(
                repaired_ask,
                assistant_message=repaired_ask.question,
                plan=plan_dict,
                engine_result=last_tool_summary,
                model_used=model_used or "controller_deterministic",
                audit=audit,
                worklog_stamps=turn_stamps,
                working_memory=last_memory_prompt,
            ), stop_reason="awaiting_user")
        audit["continuation_available"] = bool(
            last_tool_summary
            and last_tool_summary.get("status") == "completed"
        )
        if last_tool_summary and last_tool_summary.get("status") == "completed":
            msg = (
                f"ทำขั้นตอน {last_tool_summary.get('step')} เสร็จแล้ว: "
                f"{last_tool_summary.get('summary')}"
            )
        else:
            msg = "หยุดการทำงานของ orchestrator เพื่อป้องกันการวนซ้ำ"
        return await _finish(_result_from_decision(
            coerce_respond(msg),
            assistant_message=msg,
            plan=plan_dict,
            engine_result=last_tool_summary,
            model_used=model_used,
            audit=audit,
            worklog_stamps=turn_stamps,
            working_memory=last_memory_prompt,
        ), stop_reason="action_limit_reached")

    async def _handle_resolution(
        self,
        *,
        session_id: str,
        user_id: str,
        session: Dict[str, Any],
        proposal: UserResolutionProposal,
        awaiting: Mapping[str, Any],
        plan: Dict[str, Any],
        audit: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        step = str(awaiting.get("step_type") or "")
        if not step:
            return None

        if proposal.decision == "ambiguous":
            ask = _ask_from_awaiting(awaiting)
            ask = coerce_ask_user(
                ask.question + "\n\nคำตอบยังไม่ชัดเจน กรุณาเลือก อนุมัติ / ปฏิเสธ / หรือระบุการตั้งค่าที่ต้องการ",
                reason=ask.reason,
                context_key=ask.context_key,
                options=ask.options,
            )
            return {
                "result": _result_from_decision(
                    ask,
                    assistant_message=ask.question,
                    plan=plan,
                    audit={**audit, "resolution": proposal.model_dump()},
                )
            }

        if proposal.decision == "modified":
            updates = dict(proposal.context_updates or {})
            reason_code = str(
                awaiting.get("reason_code") or awaiting.get("reason") or ""
            ).strip()
            step_lower = str(step or "").strip().lower()
            # "เปลี่ยนการตั้งค่า" on aggressive clean means switch to Standard.
            if (
                not updates.get("cleaning_profile")
                and (
                    reason_code == "AGGRESSIVE_CLEANING"
                    or step_lower == "clean"
                    or str(awaiting.get("decision_key") or "") == "cleaning_confirmation"
                )
            ):
                updates["cleaning_profile"] = "standard"
            if not updates:
                ask = _ask_from_awaiting(awaiting)
                profile_options = [
                    {"id": "standard", "label": "Standard"},
                    {"id": "financial", "label": "Financial"},
                    {"id": "conservative", "label": "Conservative"},
                ]
                return {
                    "result": _result_from_decision(
                        coerce_ask_user(
                            "ต้องการเปลี่ยน cleaning profile เป็นแบบไหน?",
                            reason=reason_code or "AGGRESSIVE_CLEANING",
                            context_key="cleaning_confirmation",
                            decision_key="cleaning_confirmation",
                            options=profile_options,
                        ),
                        assistant_message="ต้องการเปลี่ยน cleaning profile เป็นแบบไหน?",
                        plan=plan,
                        audit={**audit, "resolution": proposal.model_dump()},
                    )
                }
            try:
                session = await asyncio.to_thread(
                    apply_context_updates,
                    self.client,
                    session_id=session_id,
                    user_id=user_id,
                    session=session,
                    context_updates=updates,
                )
            except Exception as exc:
                ask = _ask_from_awaiting(awaiting)
                return {
                    "result": _result_from_decision(
                        coerce_ask_user(
                            f"ยังอัปเดตการตั้งค่าไม่ได้: {exc}. {ask.question}",
                            reason=ask.reason,
                            context_key=ask.context_key,
                            options=ask.options,
                        ),
                        assistant_message=f"ยังอัปเดตการตั้งค่าไม่ได้: {exc}. {ask.question}",
                        plan=plan,
                        audit=audit,
                    )
                }
            # Input change should invalidate old confirmation fingerprint.
            try:
                await asyncio.to_thread(
                    self.engine.resolve_awaiting_user,
                    session_id,
                    step,
                    user_id=user_id,
                    resolution={
                        "decision": "modified",
                        "context_updates": updates,
                    },
                    reason="User modified setup context",
                )
            except Exception:
                # Fingerprint mismatch expected after profile change — replan.
                pass
            session = persist_active_decision_and_stamps(
                self.client,
                session_id=session_id,
                user_id=user_id,
                session=session,
                active_decision=None,
                new_stamps=[],
            )
            # Same as E2E product path: after switching profile, execute the
            # step immediately under the new fingerprint (do not wait for LLM).
            try:
                tool_result = await asyncio.to_thread(
                    self.engine.execute_step,
                    session_id,
                    step,
                    user_id=user_id,
                    session=session,
                )
            except ConfirmationRequired as exc:
                ask = _ask_from_awaiting({
                    "step_type": exc.decision.step_type,
                    "reason_code": (exc.decision.metadata or {}).get("reason_code")
                    or exc.decision.reason,
                })
                session = persist_active_decision_and_stamps(
                    self.client,
                    session_id=session_id,
                    user_id=user_id,
                    session=session,
                    active_decision=_active_decision_payload_from_ask(
                        ask,
                        step_type=exc.decision.step_type,
                        reason_code=str(
                            (exc.decision.metadata or {}).get("reason_code")
                            or exc.decision.reason
                            or ""
                        ),
                        context=(exc.decision.metadata or {}).get("context") or {},
                    ),
                    new_stamps=[],
                )
                return {
                    "result": _result_from_decision(
                        ask,
                        assistant_message=ask.question,
                        plan=plan,
                        audit=audit,
                    )
                }
            except Exception as exc:
                msg = f"เปลี่ยนการตั้งค่าแล้วแต่รัน {step} ไม่สำเร็จ: {exc}"
                return {
                    "result": _result_from_decision(
                        coerce_respond(msg),
                        assistant_message=msg,
                        plan=plan,
                        audit=audit,
                    )
                }
            summary = _tool_summary(step, tool_result)
            session = self._load_session(session_id, user_id) or session
            if getattr(tool_result, "status", None) == "awaiting_user":
                session, ask = _persist_tool_awaiting_ask(
                    self.client,
                    session_id=session_id,
                    user_id=user_id,
                    session=session,
                    step=step,
                    tool_result=tool_result,
                )
                plan = await asyncio.to_thread(
                    self.engine.get_workflow_plan,
                    session_id,
                    session=session,
                    user_id=user_id,
                )
                return {
                    "result": _result_from_decision(
                        ask,
                        assistant_message=ask.question,
                        plan=plan,
                        engine_result=summary,
                        audit=audit,
                    )
                }
            session = _leave_awaiting_answers(
                self.client,
                session_id=session_id,
                user_id=user_id,
                session=session,
            )
            return {
                "continue": True,
                "session": session,
                "last_tool_summary": summary,
            }

        if proposal.decision == "rejected":
            try:
                await asyncio.to_thread(
                    self.engine.resolve_awaiting_user,
                    session_id,
                    step,
                    user_id=user_id,
                    resolution={"decision": "rejected"},
                    reason="User rejected confirmation",
                )
            except Exception as exc:
                msg = f"ไม่สามารถปฏิเสธคำขอยืนยันได้: {exc}"
                return {
                    "result": _result_from_decision(
                        coerce_respond(msg),
                        assistant_message=msg,
                        plan=plan,
                        audit=audit,
                    )
                }
            session = persist_active_decision_and_stamps(
                self.client,
                session_id=session_id,
                user_id=user_id,
                session=session,
                active_decision=None,
                new_stamps=[],
            )
            msg = f"ยกเลิกขั้นตอน {step} ตามที่คุณต้องการแล้ว"
            plan = await asyncio.to_thread(
                self.engine.get_workflow_plan, session_id, session=session, user_id=user_id
            )
            return {
                "result": _result_from_decision(
                    coerce_respond(msg),
                    assistant_message=msg,
                    plan=plan,
                    engine_result={"step": step, "status": "rejected"},
                    audit={**audit, "resolution": proposal.model_dump()},
                )
            }

        if proposal.decision == "approved":
            try:
                await asyncio.to_thread(
                    self.engine.resolve_awaiting_user,
                    session_id,
                    step,
                    user_id=user_id,
                    resolution={"decision": "approved"},
                    reason="User approved confirmation",
                )
            except Exception as exc:
                ask = _ask_from_awaiting(awaiting)
                return {
                    "result": _result_from_decision(
                        coerce_ask_user(
                            f"คำยืนยันเดิมใช้ต่อไม่ได้ ({exc}). {ask.question}",
                            reason=str(ask.reason),
                            context_key=ask.context_key,
                            options=ask.options,
                        ),
                        assistant_message=f"คำยืนยันเดิมใช้ต่อไม่ได้ ({exc}). {ask.question}",
                        plan=plan,
                        audit=audit,
                    )
                }
            # Mirror map/validate confirmations into contract readiness flags.
            confirm_key = str(
                awaiting.get("decision_key")
                or awaiting.get("context_key")
                or ""
            ).strip()
            reason_code = str(
                awaiting.get("reason_code") or awaiting.get("reason") or ""
            ).strip()
            mirror: Dict[str, Any] = {}
            if confirm_key in {"mapping_confirmation", "mapping_confirmed"} or reason_code == "AMBIGUOUS_MAPPING":
                mirror["mapping_confirmed"] = True
            if confirm_key in {"contract_confirmation", "business_context_reviewed"} or reason_code == "BUSINESS_CONTRACT_CHANGE":
                mirror["business_context_reviewed"] = True
            if mirror:
                try:
                    session = await asyncio.to_thread(
                        apply_context_updates,
                        self.client,
                        session_id=session_id,
                        user_id=user_id,
                        session=session,
                        context_updates=mirror,
                    )
                except Exception:
                    pass
            # Execute the approved step immediately under engine authority.
            try:
                tool_result = await asyncio.to_thread(
                    self.engine.execute_step,
                    session_id,
                    step,
                    user_id=user_id,
                    session=session,
                )
            except ConfirmationRequired as exc:
                ask = _ask_from_awaiting({
                    "step_type": exc.decision.step_type,
                    "reason_code": (exc.decision.metadata or {}).get("reason_code")
                    or exc.decision.reason,
                })
                return {
                    "result": _result_from_decision(
                        ask,
                        assistant_message=ask.question,
                        plan=plan,
                        audit=audit,
                    )
                }
            except Exception as exc:
                msg = f"อนุมัติแล้วแต่รัน {step} ไม่สำเร็จ: {exc}"
                return {
                    "result": _result_from_decision(
                        coerce_respond(msg),
                        assistant_message=msg,
                        plan=plan,
                        audit=audit,
                    )
                }
            summary = _tool_summary(step, tool_result)
            session = self._load_session(session_id, user_id) or session
            if getattr(tool_result, "status", None) == "awaiting_user":
                session, ask = _persist_tool_awaiting_ask(
                    self.client,
                    session_id=session_id,
                    user_id=user_id,
                    session=session,
                    step=step,
                    tool_result=tool_result,
                )
                plan = await asyncio.to_thread(
                    self.engine.get_workflow_plan,
                    session_id,
                    session=session,
                    user_id=user_id,
                )
                return {
                    "result": _result_from_decision(
                        ask,
                        assistant_message=ask.question,
                        plan=plan,
                        engine_result=summary,
                        audit=audit,
                    )
                }
            session = _leave_awaiting_answers(
                self.client,
                session_id=session_id,
                user_id=user_id,
                session=session,
            )
            session = persist_active_decision_and_stamps(
                self.client,
                session_id=session_id,
                user_id=user_id,
                session=session,
                active_decision=None,
                new_stamps=[],
            )
            return {
                "continue": True,
                "session": session,
                "last_tool_summary": summary,
            }

        return None


async def orchestrate_workflow_message(
    *,
    session_id: str,
    user_id: str,
    message: str = "",
    messages: Optional[List[Mapping[str, Any]]] = None,
    tier: str = "free",
    locale: str = "th",
    client: Any | None = None,
    llm: LlmClient | None = None,
    llm_decision_override: Any = None,
    orchestration_resolution: Optional[Mapping[str, Any]] = None,
    setup_intent: Optional[str] = None,
    settlement_key: Optional[str] = None,
) -> OrchestratorResult:
    orch = WorkflowOrchestrator(client=client, llm=llm)
    return await orch.handle_message(
        session_id=session_id,
        user_id=user_id,
        message=message,
        messages=messages,
        tier=tier,
        locale=locale,
        llm_decision_override=llm_decision_override,
        orchestration_resolution=orchestration_resolution,
        setup_intent=setup_intent,
        settlement_key=settlement_key,
    )


def should_route_to_orchestrator(
    *,
    chat_request: Any,
    session: Optional[Mapping[str, Any]],
) -> bool:
    if not settings.ENABLE_CONVERSATIONAL_DATA_SETUP:
        return False
    if chat_request.agent_session_id:
        return False
    if not session:
        return False
    return str(session.get("status") or "") != "ready"
