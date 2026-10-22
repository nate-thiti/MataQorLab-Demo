"""Workflow Engine — authority for transitions, deps, reuse, retry, stale.

Caller contract (Phase 4.5)
---------------------------
Allowed product callers:
  - process_data_setup_session (compatibility sequencer)
  - data_setup_worker
  - future AI Orchestrator (via execute_step / get_next_action only)
  - explicit admin workflow control

Not allowed:
  - AI → raw setup tools (inspect_source / clean_data / …)
  - frontend → raw setup tools
  - chat → execute_etl_recipe for data-setup workflow

Schedule/manual ETL remains on execute_etl_recipe (separate boundary).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Union

from app.core.supabase import get_supabase_client
from app.services.tools.registry import UnknownStepError, get_step_entry, resolve_step_type
from app.services.tools.types import ToolResult
from app.services.workflow.capability import ensure_workflow_persistence_ready
from app.services.workflow.dependencies import (
    invalidation_targets,
    requires,
)
from app.services.workflow.models import (
    MAX_ENGINE_ACTIONS,
    SETUP_SEQUENCE,
    ConfirmationDecision,
    WorkflowDecision,
    WorkflowErrorCode,
    WorkflowPlan,
    WorkflowPlanStep,
    WorkflowStepStatus,
    WorkflowStepType,
)
from app.services.workflow.orchestrator_context import build_orchestrator_workflow_context
from app.services.workflow.policies import (
    approval_matches_proposed,
    build_confirmation_fingerprint,
    build_step_fingerprint,
    can_skip,
    cleaned_artifact_present,
    dependency_satisfied,
    evaluate_confirmation_requirement,
    fingerprints_match,
    has_input_fingerprint,
)
from app.services.workflow import runners
from app.services.workflow.events import (
    STEP_AWAITING_USER,
    STEP_REUSED,
    STEP_STALE,
    WORKFLOW_BLOCKED,
    WORKFLOW_READY,
    emit_workflow_event,
    timed_step,
)
from app.services.workflow.state import (
    begin_step,
    execute_persisted_tool_step,
    fail_step,
    get_latest_step,
    get_resume_state,
    is_reusable,
    mark_step_awaiting_user,
    mark_step_ready,
    mark_step_stale,
    skip_step as persist_skip_step,
    update_session_summary,
)

logger = logging.getLogger("mataqorlab.workflow.engine")


class ConfirmationRequired(RuntimeError):
    """Raised when execute_step pauses for user confirmation (tool not run)."""

    def __init__(self, decision: WorkflowDecision):
        self.decision = decision
        super().__init__(decision.reason or "Confirmation required")


class WorkflowEngine:
    """Deterministic workflow control plane for data_setup_sessions."""

    def __init__(self, *, client: Any | None = None, skip_capability_check: bool = False):
        self.client = client or get_supabase_client()
        self._context: Dict[str, Any] = {}
        if not skip_capability_check:
            ensure_workflow_persistence_ready(self.client)

    # ------------------------------------------------------------------ plan
    def get_workflow_plan(
        self,
        session_id: str,
        *,
        session: Optional[Mapping[str, Any]] = None,
        user_id: Optional[str] = None,
        as_model: bool = False,
    ) -> Union[Dict[str, Any], WorkflowPlan]:
        session = dict(session or self._load_session(session_id, user_id) or {})
        resume = get_resume_state(session_id, client=self.client)
        by_type = resume.get("steps") or {}
        steps_out: List[WorkflowPlanStep] = []
        for step in SETUP_SEQUENCE:
            latest = by_type.get(step.value) or {}
            status = str(latest.get("status") or WorkflowStepStatus.PENDING.value)
            output = latest.get("output") or {}
            summary = None
            if isinstance(output, dict):
                summary = output.get("summary")
            reusable = bool(
                latest
                and self._is_reuse_valid(step.value, latest, session)
            )
            steps_out.append(WorkflowPlanStep(
                step_type=step.value,
                status=status,
                version=latest.get("version"),
                attempt=latest.get("attempt"),
                reusable=reusable,
                retryable=status in {
                    WorkflowStepStatus.FAILED.value,
                    WorkflowStepStatus.STALE.value,
                },
                requires_confirmation=bool(latest.get("requires_confirmation")),
                stale_reason=(
                    latest.get("reason")
                    if status == WorkflowStepStatus.STALE.value
                    else None
                ),
                latest_summary=str(summary)[:300] if summary else None,
            ))
        decision = self.get_next_action(session_id, session=session, user_id=user_id)
        status = "ready" if session.get("status") == "ready" else "in_progress"
        if decision.action == "complete":
            status = "ready"
        elif decision.action == "awaiting_user":
            status = "awaiting_user"
        elif decision.action == "blocked":
            status = "blocked"

        awaiting_user = None
        blockers: List[Dict[str, Any]] = []
        if decision.action == "awaiting_user":
            awaiting_user = {
                "step_type": decision.step_type,
                "reason": decision.reason,
                "reason_code": (decision.metadata or {}).get("reason_code") or decision.reason,
                "context": (decision.metadata or {}).get("context") or {},
            }
        if decision.action == "blocked":
            blockers.append({
                "step_type": decision.step_type,
                "reason": decision.reason,
                "error_code": decision.error_code,
            })

        plan = WorkflowPlan(
            session_id=session_id,
            status=status,
            current_step=decision.step_type or resume.get("next_step"),
            next_action=decision,
            steps=steps_out,
            blockers=blockers,
            awaiting_user=awaiting_user,
            last_failed_step=resume.get("last_failed_step"),
        )
        if as_model:
            return plan
        # Backward-compatible dict (also exposes step alias used by Phase 4 tests).
        payload = plan.model_dump()
        payload["steps"] = [
            {
                "step": item.step_type,
                "step_type": item.step_type,
                "status": item.status,
                "version": item.version,
                "attempt": item.attempt,
                "reusable": item.reusable,
                "retryable": item.retryable,
                "requires_confirmation": item.requires_confirmation,
                "stale_reason": item.stale_reason,
                "latest_summary": item.latest_summary,
                "reason": item.stale_reason,
            }
            for item in steps_out
        ]
        payload["next_action"] = decision.model_dump()
        return payload

    def to_orchestrator_context(
        self,
        session_id: str,
        *,
        session: Optional[Mapping[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        plan = self.get_workflow_plan(
            session_id, session=session, user_id=user_id, as_model=True
        )
        assert isinstance(plan, WorkflowPlan)
        return build_orchestrator_workflow_context(plan)

    def get_next_action(
        self,
        session_id: str,
        *,
        session: Optional[Mapping[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> WorkflowDecision:
        session = dict(session or self._load_session(session_id, user_id) or {})
        if session.get("status") == "ready":
            return WorkflowDecision(
                action="complete",
                step_type=WorkflowStepType.FINALIZE.value,
                reason="Session is already ready.",
            )

        # Sync fingerprints → mark stale before planning (incl. awaiting_user).
        self.sync_input_validity(session_id, session)

        resume = get_resume_state(session_id, client=self.client)
        by_type: Dict[str, Dict[str, Any]] = resume.get("steps") or {}

        for step_type, latest in by_type.items():
            if str(latest.get("status")) == WorkflowStepStatus.AWAITING_USER.value:
                meta = (latest.get("output") or {}).get("metadata") or {}
                return WorkflowDecision(
                    action="awaiting_user",
                    step_type=step_type,
                    reason=str(latest.get("reason") or "Awaiting user confirmation"),
                    error_code=WorkflowErrorCode.STEP_AWAITING_USER.value,
                    metadata={
                        "context": meta,
                        "reason_code": meta.get("reason_code") or latest.get("reason"),
                        "confirmation_fingerprint": (latest.get("input") or {}).get(
                            "confirmation_fingerprint"
                        ),
                    },
                )
            if str(latest.get("status")) == WorkflowStepStatus.RUNNING.value:
                return WorkflowDecision(
                    action="blocked",
                    step_type=step_type,
                    reason=f"Step {step_type} is already running.",
                    error_code=WorkflowErrorCode.STEP_ALREADY_RUNNING.value,
                )

        for step in SETUP_SEQUENCE:
            step_type = step.value
            latest = by_type.get(step_type)
            status = str((latest or {}).get("status") or WorkflowStepStatus.PENDING.value)

            if status == WorkflowStepStatus.READY.value:
                # Approved confirmation waiting to execute.
                ok, missing = self._dependencies_ok(step_type, by_type)
                if not ok:
                    return WorkflowDecision(
                        action="blocked",
                        step_type=step_type,
                        reason=f"Dependencies not satisfied: {', '.join(sorted(missing))}",
                        error_code=WorkflowErrorCode.DEPENDENCY_NOT_SATISFIED.value,
                        metadata={"missing": sorted(missing)},
                    )
                return WorkflowDecision(
                    action="execute",
                    step_type=step_type,
                    reason=f"Execute {step_type} after confirmation.",
                )

            if status in {
                WorkflowStepStatus.COMPLETED.value,
                WorkflowStepStatus.SKIPPED.value,
            }:
                if self._is_reuse_valid(step_type, latest, session):
                    continue
                # Missing fingerprint or invalid — force re-exec (not silent reuse).
                if latest and status != WorkflowStepStatus.STALE.value:
                    try:
                        mark_step_stale(
                            str(latest["id"]),
                            reason=(
                                "Missing input fingerprint — not reusable"
                                if not has_input_fingerprint(latest.get("input") or {})
                                else "Input fingerprint or artifact no longer valid"
                            ),
                            client=self.client,
                        )
                    except Exception:
                        pass
                status = WorkflowStepStatus.STALE.value

            if status in {
                WorkflowStepStatus.PENDING.value,
                WorkflowStepStatus.FAILED.value,
                WorkflowStepStatus.STALE.value,
            }:
                ok, missing = self._dependencies_ok(step_type, by_type)
                if not ok:
                    return WorkflowDecision(
                        action="blocked",
                        step_type=step_type,
                        reason=f"Dependencies not satisfied: {', '.join(sorted(missing))}",
                        error_code=(
                            WorkflowErrorCode.STALE_DEPENDENCY.value
                            if any(
                                str((by_type.get(m) or {}).get("status"))
                                == WorkflowStepStatus.STALE.value
                                for m in missing
                            )
                            else WorkflowErrorCode.DEPENDENCY_NOT_SATISFIED.value
                        ),
                        metadata={"missing": sorted(missing)},
                    )
                action = "retry" if status == WorkflowStepStatus.FAILED.value else "execute"
                return WorkflowDecision(
                    action=action,
                    step_type=step_type,
                    reason=(
                        f"Retry {step_type} after failure."
                        if action == "retry"
                        else f"Execute {step_type}."
                    ),
                )

        finalize = by_type.get(WorkflowStepType.FINALIZE.value) or {}
        if str(finalize.get("status")) in {
            WorkflowStepStatus.COMPLETED.value,
            WorkflowStepStatus.SKIPPED.value,
        }:
            return WorkflowDecision(
                action="complete",
                step_type=WorkflowStepType.FINALIZE.value,
                reason="All workflow steps are complete.",
            )
        return WorkflowDecision(
            action="blocked",
            step_type=WorkflowStepType.FINALIZE.value,
            reason="Workflow incomplete without a runnable next step.",
            error_code=WorkflowErrorCode.DEPENDENCY_NOT_SATISFIED.value,
        )

    def can_execute_step(
        self,
        session_id: str,
        step_type: str,
        *,
        session: Optional[Mapping[str, Any]] = None,
    ) -> WorkflowDecision:
        try:
            step = resolve_step_type(step_type)
        except UnknownStepError:
            return WorkflowDecision(
                action="blocked",
                step_type=str(step_type),
                reason=f"Unknown step: {step_type}",
                error_code=WorkflowErrorCode.UNKNOWN_STEP.value,
            )
        get_step_entry(step)  # fail closed if missing registry entry
        session = dict(session or self._load_session(session_id) or {})
        resume = get_resume_state(session_id, client=self.client)
        by_type = resume.get("steps") or {}

        # Any awaiting_user step blocks the whole workflow product path.
        for other_type, other in by_type.items():
            if str(other.get("status")) == WorkflowStepStatus.AWAITING_USER.value:
                return WorkflowDecision(
                    action="awaiting_user",
                    step_type=other_type,
                    reason=str(other.get("reason") or "Awaiting user"),
                    error_code=WorkflowErrorCode.STEP_AWAITING_USER.value,
                )

        latest = by_type.get(step)
        if latest and str(latest.get("status")) == WorkflowStepStatus.RUNNING.value:
            return WorkflowDecision(
                action="blocked",
                step_type=step,
                reason="Step already running",
                error_code=WorkflowErrorCode.STEP_ALREADY_RUNNING.value,
            )
        ok, missing = self._dependencies_ok(step, by_type)
        if not ok:
            return WorkflowDecision(
                action="blocked",
                step_type=step,
                reason=f"Dependencies not satisfied: {', '.join(sorted(missing))}",
                error_code=WorkflowErrorCode.DEPENDENCY_NOT_SATISFIED.value,
                metadata={"missing": sorted(missing)},
            )
        if (
            latest
            and is_reusable(latest)
            and self._is_reuse_valid(step, latest, session)
        ):
            return WorkflowDecision(
                action="reuse",
                step_type=step,
                reason=f"Latest {step} result is reusable.",
            )
        return WorkflowDecision(
            action="execute",
            step_type=step,
            reason=f"{step} is executable.",
        )

    # --------------------------------------------------------------- execute
    def execute_step(
        self,
        session_id: str,
        step_type: str,
        *,
        user_id: str,
        session: Optional[Mapping[str, Any]] = None,
        force_new_version: bool = False,
    ) -> ToolResult:
        decision = self.can_execute_step(session_id, step_type, session=session)
        if decision.action == "reuse":
            latest = get_latest_step(session_id, decision.step_type, client=self.client) or {}
            output = latest.get("output") or {}
            self._hydrate_context_from_output(decision.step_type or "", output)
            logger.info(
                "workflow_reuse",
                extra={
                    "session_id": session_id,
                    "step_type": decision.step_type,
                    "version": latest.get("version"),
                    "attempt": latest.get("attempt"),
                    "reason": decision.reason,
                },
            )
            emit_workflow_event(
                STEP_REUSED,
                session_id=session_id,
                step_type=decision.step_type,
                status="completed",
                version=latest.get("version"),
                attempt=latest.get("attempt"),
                reason_code="REUSE",
                source_type=str((session or {}).get("source_type") or "") or None,
            )
            try:
                return ToolResult(**{
                    k: output.get(k)
                    for k in (
                        "tool", "status", "summary", "findings", "warnings",
                        "artifacts", "metadata", "suggested_next_actions",
                    )
                    if k in output or k == "tool"
                })
            except Exception:
                return ToolResult(
                    tool=str(decision.step_type),
                    status="completed",
                    summary=decision.reason,
                    artifacts=(output.get("artifacts") or {}),
                )
        if decision.action == "awaiting_user":
            raise ConfirmationRequired(decision)
        if decision.action != "execute" and decision.action != "retry":
            raise RuntimeError(
                f"{decision.error_code or 'BLOCKED'}: {decision.reason}"
            )

        step = resolve_step_type(step_type)
        session = dict(session or self._load_session(session_id, user_id) or {})
        fingerprint = build_step_fingerprint(
            step,
            session=session,
            dataset_key=self._context.get("dataset_key"),
            cleaning_profile=session.get("cleaning_profile"),
        )

        confirmation = evaluate_confirmation_requirement(
            session,
            step,
            proposed_input=fingerprint,
        )
        if confirmation.required:
            latest = get_latest_step(session_id, step, client=self.client)
            if not approval_matches_proposed(
                latest, str(confirmation.confirmation_fingerprint or "")
            ):
                await_decision = self._pause_for_confirmation(
                    session_id,
                    step,
                    user_id=user_id,
                    confirmation=confirmation,
                    fingerprint=fingerprint,
                    latest=latest,
                )
                raise ConfirmationRequired(await_decision)

        bump = force_new_version or (
            str((get_latest_step(session_id, step, client=self.client) or {}).get("status"))
            == WorkflowStepStatus.STALE.value
        )

        def runner():
            return self._dispatch_runner(step, user_id, session_id, session)

        logger.info(
            "workflow_execute",
            extra={
                "session_id": session_id,
                "step_type": step,
                "reason": decision.reason,
                "bump_version": bump,
            },
        )
        latest_before = get_latest_step(session_id, step, client=self.client) or {}
        with timed_step(
            session_id=session_id,
            step_type=step,
            source_type=str(session.get("source_type") or "") or None,
            version=latest_before.get("version"),
            attempt=latest_before.get("attempt"),
            is_retry=decision.action == "retry",
        ):
            _row, result, _reused, extras = execute_persisted_tool_step(
                session_id=session_id,
                user_id=user_id,
                step_type=WorkflowStepType(step),
                input_payload=fingerprint,
                runner=runner,
                client=self.client,
                allow_reuse=False,
                bump_version=bump,
            )
            if result is None:
                raise RuntimeError(f"{step} produced no result")
            if result.status == "failed":
                raise RuntimeError(result.summary or f"{step} failed")
        if extras:
            self._context["cleaned_handle"] = extras[0]
        if result and result.artifacts:
            self._hydrate_context_from_output(step, {"artifacts": result.artifacts})
        return result

    def _pause_for_confirmation(
        self,
        session_id: str,
        step: str,
        *,
        user_id: str,
        confirmation: ConfirmationDecision,
        fingerprint: Mapping[str, Any],
        latest: Optional[Mapping[str, Any]],
    ) -> WorkflowDecision:
        input_payload = {
            **dict(fingerprint),
            "confirmation_fingerprint": confirmation.confirmation_fingerprint,
            "reason_code": confirmation.reason_code,
        }
        if latest and str(latest.get("status")) == WorkflowStepStatus.AWAITING_USER.value:
            row = dict(latest)
        else:
            row = begin_step(
                session_id,
                step,
                input_payload=input_payload,
                client=self.client,
            )
            if is_reusable(row):
                # Unexpected completed reclaim — do not treat as confirmation pause.
                raise RuntimeError("Unexpected reusable step during confirmation pause")
            output = ToolResult(
                tool=get_step_entry(step)["tool_name"],
                status="awaiting_user",
                summary=confirmation.reason or confirmation.reason_code or "Confirmation required",
                metadata={
                    "reason_code": confirmation.reason_code,
                    "context": confirmation.context,
                    "confirmation_fingerprint": confirmation.confirmation_fingerprint,
                },
            )
            row = mark_step_awaiting_user(
                str(row["id"]),
                reason=str(confirmation.reason_code or confirmation.reason or "CONFIRMATION_REQUIRED"),
                output=output,
                client=self.client,
            )
        update_session_summary(
            session_id, user_id, next_action=step, client=self.client
        )
        logger.info(
            "workflow_awaiting_user",
            extra={
                "session_id": session_id,
                "step_type": step,
                "reason": confirmation.reason_code,
                "version": row.get("version"),
                "attempt": row.get("attempt"),
            },
        )
        emit_workflow_event(
            STEP_AWAITING_USER,
            session_id=session_id,
            step_type=step,
            status="awaiting_user",
            version=row.get("version"),
            attempt=row.get("attempt"),
            reason_code=str(confirmation.reason_code or "CONFIRMATION_REQUIRED"),
        )
        return WorkflowDecision(
            action="awaiting_user",
            step_type=step,
            reason=str(confirmation.reason_code or confirmation.reason),
            error_code=WorkflowErrorCode.CONFIRMATION_REQUIRED.value,
            metadata={
                "reason_code": confirmation.reason_code,
                "context": confirmation.context,
                "confirmation_fingerprint": confirmation.confirmation_fingerprint,
            },
        )

    def retry_step(
        self,
        session_id: str,
        step_type: str,
        *,
        user_id: str,
        session: Optional[Mapping[str, Any]] = None,
    ) -> ToolResult:
        step = resolve_step_type(step_type)
        latest = get_latest_step(session_id, step, client=self.client)
        if not latest or str(latest.get("status")) not in {
            WorkflowStepStatus.FAILED.value,
            WorkflowStepStatus.STALE.value,
        }:
            raise RuntimeError(
                f"{WorkflowErrorCode.STEP_NOT_RETRYABLE.value}: {step} is not retryable"
            )
        return self.execute_step(
            session_id,
            step,
            user_id=user_id,
            session=session,
            force_new_version=str(latest.get("status")) == WorkflowStepStatus.STALE.value,
        )

    def skip_step(
        self,
        session_id: str,
        step_type: str,
        *,
        user_id: str,
        reason: str,
        session: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        step = resolve_step_type(step_type)
        if not can_skip(step):
            raise RuntimeError(
                f"{WorkflowErrorCode.SKIP_NOT_ALLOWED.value}: {step} cannot be skipped"
            )
        decision = self.can_execute_step(session_id, step, session=session)
        if decision.action == "blocked":
            raise RuntimeError(f"{decision.error_code}: {decision.reason}")
        if decision.action == "awaiting_user":
            raise RuntimeError(
                f"{WorkflowErrorCode.STEP_AWAITING_USER.value}: resolve confirmation first"
            )
        fingerprint = build_step_fingerprint(
            step,
            session=dict(session or self._load_session(session_id, user_id) or {}),
            dataset_key=self._context.get("dataset_key"),
        )
        row = begin_step(
            session_id,
            step,
            input_payload={**fingerprint, "skip": True},
            client=self.client,
        )
        if is_reusable(row):
            return row
        result = ToolResult(
            tool=get_step_entry(step)["tool_name"],
            status="skipped",
            summary=reason,
            metadata={"skipped": True},
        )
        completed = persist_skip_step(
            str(row["id"]),
            reason=reason,
            output=result,
            client=self.client,
        )
        logger.info(
            "workflow_skip",
            extra={
                "session_id": session_id,
                "step_type": step,
                "version": completed.get("version"),
                "attempt": completed.get("attempt"),
                "reason": reason,
            },
        )
        update_session_summary(
            session_id, user_id, next_action=None, client=self.client
        )
        return completed

    def mark_awaiting_user(
        self,
        session_id: str,
        step_type: str,
        *,
        user_id: str,
        reason: str,
        context: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        step = resolve_step_type(step_type)
        session = dict(self._load_session(session_id, user_id) or {})
        fingerprint = build_step_fingerprint(
            step,
            session=session,
            dataset_key=self._context.get("dataset_key"),
        )
        conf_fp = build_confirmation_fingerprint(
            step,
            session=session,
            proposed_input=fingerprint,
            reason_code=reason,
        )
        latest = get_latest_step(session_id, step, client=self.client)
        if not latest:
            latest = begin_step(
                session_id,
                step,
                input_payload={
                    **fingerprint,
                    "awaiting_user": True,
                    "confirmation_fingerprint": conf_fp,
                    "reason_code": reason,
                },
                client=self.client,
            )
        output = ToolResult(
            tool=get_step_entry(step)["tool_name"],
            status="awaiting_user",
            summary=reason,
            metadata={
                **dict(context or {}),
                "reason_code": reason,
                "confirmation_fingerprint": conf_fp,
            },
        )
        row = mark_step_awaiting_user(
            str(latest["id"]),
            reason=reason,
            output=output,
            client=self.client,
        )
        update_session_summary(
            session_id,
            user_id,
            next_action=step,
            client=self.client,
        )
        logger.info(
            "workflow_awaiting_user",
            extra={
                "session_id": session_id,
                "step_type": step,
                "reason": reason,
            },
        )
        return row

    def resolve_awaiting_user(
        self,
        session_id: str,
        step_type: str,
        *,
        user_id: str,
        resolution: Optional[Mapping[str, Any]] = None,
        reason: str = "User resolved confirmation",
    ) -> Dict[str, Any]:
        """Structured confirmation resolution.

        ``resolution.decision``: approved | rejected | modified
        Confirmation is bound to ``confirmation_fingerprint``; input drift
        invalidates prior approval.
        """
        step = resolve_step_type(step_type)
        latest = get_latest_step(session_id, step, client=self.client)
        if not latest or str(latest.get("status")) != WorkflowStepStatus.AWAITING_USER.value:
            raise RuntimeError(
                f"{WorkflowErrorCode.STEP_NOT_RETRYABLE.value}: {step} is not awaiting user"
            )

        payload = dict(resolution or {"decision": "approved"})
        decision = str(payload.get("decision") or "approved").strip().lower()
        session = dict(self._load_session(session_id, user_id) or {})
        fingerprint = build_step_fingerprint(
            step,
            session=session,
            dataset_key=self._context.get("dataset_key"),
            cleaning_profile=session.get("cleaning_profile"),
        )
        stored_fp = (latest.get("input") or {}).get("confirmation_fingerprint")
        reason_code = (latest.get("input") or {}).get("reason_code") or latest.get("reason")
        current_fp = build_confirmation_fingerprint(
            step,
            session=session,
            proposed_input=fingerprint,
            reason_code=str(reason_code or ""),
        )

        if stored_fp and stored_fp != current_fp:
            mark_step_stale(
                str(latest["id"]),
                reason="Confirmation invalidated — proposed inputs changed",
                client=self.client,
            )
            logger.info(
                "workflow_confirmation_stale",
                extra={
                    "session_id": session_id,
                    "step_type": step,
                    "reason": "fingerprint_mismatch",
                },
            )
            raise RuntimeError(
                f"{WorkflowErrorCode.CONFIRMATION_STALE.value}: "
                "pending confirmation no longer matches current inputs"
            )

        audit = {
            "decision": decision,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "confirmation_fingerprint": stored_fp or current_fp,
            "context_updates": dict(payload.get("context_updates") or {}),
            "note": reason,
        }

        if decision == "rejected":
            failed = fail_step(
                str(latest["id"]),
                error=reason or "User rejected confirmation",
                error_code=WorkflowErrorCode.CONFIRMATION_REJECTED.value,
                client=self.client,
            )
            # Persist audit on failed output.
            from app.core.json_safety import to_json_safe

            output = dict(failed.get("output") or {})
            meta = dict(output.get("metadata") or {})
            meta["resolution"] = audit
            output["metadata"] = meta
            self.client.table("workflow_steps").update({
                "output": to_json_safe(output),
                "reason": (reason or "rejected")[:2000],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", latest["id"]).execute()
            update_session_summary(
                session_id, user_id, next_action=None, last_failed_step=step, client=self.client
            )
            logger.info(
                "workflow_confirmation_rejected",
                extra={"session_id": session_id, "step_type": step},
            )
            from app.services.workflow.events import STEP_RESOLVED

            emit_workflow_event(
                STEP_RESOLVED,
                session_id=session_id,
                step_type=step,
                status="failed",
                version=latest.get("version"),
                attempt=latest.get("attempt"),
                reason_code="CONFIRMATION_REJECTED",
            )
            return {**failed, "resolution": audit, "engine_action": "blocked"}

        if decision not in {"approved", "modified"}:
            raise RuntimeError(f"Unknown resolution decision: {decision}")

        # modified may carry context_updates for callers to apply to session.
        row = mark_step_ready(
            str(latest["id"]),
            reason=reason,
            client=self.client,
        )
        from app.core.json_safety import to_json_safe

        output = dict((latest.get("output") or {}), **(row.get("output") or {}))
        meta = dict(output.get("metadata") or {})
        meta["resolution"] = audit
        output["metadata"] = meta
        # Keep confirmation fingerprint on input for execute-time match.
        input_payload = dict(latest.get("input") or {})
        input_payload["confirmation_fingerprint"] = stored_fp or current_fp
        updated = (
            self.client.table("workflow_steps")
            .update({
                "output": to_json_safe(output),
                "input": to_json_safe(input_payload),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("id", latest["id"])
            .execute()
        )
        row = (updated.data or [row])[0]
        update_session_summary(
            session_id, user_id, next_action=step, client=self.client
        )
        from app.services.workflow.events import STEP_RESOLVED

        emit_workflow_event(
            STEP_RESOLVED,
            session_id=session_id,
            step_type=step,
            status="ready",
            version=latest.get("version"),
            attempt=latest.get("attempt"),
            reason_code=str(decision).upper(),
        )
        logger.info(
            "workflow_confirmation_approved",
            extra={
                "session_id": session_id,
                "step_type": step,
                "decision": decision,
            },
        )
        return {**row, "resolution": audit, "engine_action": "ready"}

    def invalidate_step(
        self,
        session_id: str,
        step_type: str,
        *,
        reason: str,
    ) -> Optional[Dict[str, Any]]:
        step = resolve_step_type(step_type)
        latest = get_latest_step(session_id, step, client=self.client)
        if not latest:
            return None
        status = str(latest.get("status") or "")
        if status not in {
            WorkflowStepStatus.COMPLETED.value,
            WorkflowStepStatus.SKIPPED.value,
            WorkflowStepStatus.AWAITING_USER.value,
            WorkflowStepStatus.READY.value,
        }:
            return latest
        if status == WorkflowStepStatus.STALE.value:
            return latest
        logger.info(
            "workflow_invalidate",
            extra={
                "session_id": session_id,
                "step_type": step,
                "version": latest.get("version"),
                "attempt": latest.get("attempt"),
                "reason": reason,
            },
        )
        reason_code = (
            WorkflowErrorCode.ARTIFACT_MISSING.value
            if "artifact missing" in reason.lower()
            else "STALE"
        )
        emit_workflow_event(
            STEP_STALE,
            session_id=session_id,
            step_type=step,
            status="stale",
            version=latest.get("version"),
            attempt=latest.get("attempt"),
            reason_code=reason_code,
            metadata={"reason": reason[:200]},
        )
        return mark_step_stale(str(latest["id"]), reason=reason, client=self.client)

    def invalidate_downstream(
        self,
        session_id: str,
        from_step: str,
        *,
        reason: str,
    ) -> List[Dict[str, Any]]:
        step = resolve_step_type(from_step)
        updated: List[Dict[str, Any]] = []
        for target in sorted(invalidation_targets(step)):
            row = self.invalidate_step(session_id, target, reason=reason)
            if row and str(row.get("status")) == WorkflowStepStatus.STALE.value:
                updated.append(row)
        return updated

    def sync_input_validity(
        self,
        session_id: str,
        session: Mapping[str, Any],
    ) -> None:
        """Mark completed/awaiting steps stale when fingerprints diverge."""
        resume = get_resume_state(session_id, client=self.client)
        by_type = resume.get("steps") or {}
        dataset_key = self._context.get("dataset_key") or runners.dataset_key_from_context(
            self._context, session
        )
        for step in SETUP_SEQUENCE:
            latest = by_type.get(step.value)
            if not latest:
                continue
            status = str(latest.get("status") or "")
            fp = build_step_fingerprint(
                step.value,
                session=session,
                dataset_key=dataset_key,
                cleaning_profile=session.get("cleaning_profile"),
            )
            stored = latest.get("input") or {}

            if status == WorkflowStepStatus.AWAITING_USER.value:
                reason_code = stored.get("reason_code") or latest.get("reason")
                current_conf = build_confirmation_fingerprint(
                    step.value,
                    session=session,
                    proposed_input=fp,
                    reason_code=str(reason_code or ""),
                )
                stored_conf = stored.get("confirmation_fingerprint")
                if stored_conf and stored_conf != current_conf:
                    self.invalidate_step(
                        session_id,
                        step.value,
                        reason="Pending confirmation invalidated by input change",
                    )
                    self.invalidate_downstream(
                        session_id,
                        step.value,
                        reason=f"Confirmation for {step.value} invalidated",
                    )
                continue

            if not is_reusable(latest) and status != WorkflowStepStatus.READY.value:
                continue

            if status == WorkflowStepStatus.READY.value:
                # Ready-after-approval must still match current inputs.
                if has_input_fingerprint(stored) and not fingerprints_match(stored, fp):
                    self.invalidate_step(
                        session_id,
                        step.value,
                        reason="Approved step inputs changed before execution",
                    )
                continue

            if fingerprints_match(stored, fp):
                if (
                    step == WorkflowStepType.CLEAN
                    and not cleaned_artifact_present(latest)
                ):
                    self.invalidate_step(
                        session_id,
                        step.value,
                        reason="Cleaned artifact missing",
                    )
                    self.invalidate_downstream(
                        session_id,
                        step.value,
                        reason="Cleaned artifact missing",
                    )
                continue
            # Only stale when prior input had fingerprint keys.
            if not has_input_fingerprint(stored):
                continue
            self.invalidate_step(
                session_id,
                step.value,
                reason="Step input fingerprint changed",
            )
            self.invalidate_downstream(
                session_id,
                step.value,
                reason=f"Upstream {step.value} inputs changed",
            )

    def run_until_idle(
        self,
        session_id: str,
        *,
        user_id: str,
        session: Optional[Mapping[str, Any]] = None,
        max_actions: int = MAX_ENGINE_ACTIONS,
    ) -> WorkflowDecision:
        """Compatibility loop used by process_data_setup_session."""
        session = dict(session or self._load_session(session_id, user_id) or {})
        last = WorkflowDecision(action="blocked", reason="No actions taken")
        for _ in range(max(1, int(max_actions))):
            last = self.get_next_action(session_id, session=session, user_id=user_id)
            if last.action in {"complete", "blocked", "awaiting_user"}:
                return last
            if last.action == "reuse":
                if last.step_type:
                    latest = get_latest_step(
                        session_id, last.step_type, client=self.client
                    ) or {}
                    self._hydrate_context_from_output(
                        last.step_type, latest.get("output") or {}
                    )
                continue
            if last.action in {"execute", "retry"} and last.step_type:
                try:
                    self.execute_step(
                        session_id,
                        last.step_type,
                        user_id=user_id,
                        session=session,
                    )
                except ConfirmationRequired as exc:
                    return exc.decision
                session = dict(self._load_session(session_id, user_id) or session)
                continue
            return last
        return WorkflowDecision(
            action="blocked",
            reason="Exceeded max workflow actions",
            error_code=WorkflowErrorCode.MAX_ACTIONS_EXCEEDED.value,
        )

    # ------------------------------------------------------------- internals
    def _load_session(
        self,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        query = (
            self.client.table("data_setup_sessions")
            .select("*")
            .eq("id", session_id)
        )
        if user_id:
            query = query.eq("user_id", user_id)
        response = query.limit(1).execute()
        rows = response.data or []
        return rows[0] if rows else None

    def _dependencies_ok(
        self,
        step_type: str,
        by_type: Mapping[str, Mapping[str, Any]],
    ) -> tuple[bool, List[str]]:
        missing: List[str] = []
        for dep in sorted(requires(step_type)):
            row = by_type.get(dep)
            if not dependency_satisfied(row):
                missing.append(dep)
            elif str((row or {}).get("status")) == WorkflowStepStatus.STALE.value:
                missing.append(dep)
        return (not missing, missing)

    def _is_reuse_valid(
        self,
        step_type: str,
        latest: Mapping[str, Any],
        session: Mapping[str, Any],
    ) -> bool:
        if not is_reusable(latest):
            return False
        if str(latest.get("status")) == WorkflowStepStatus.STALE.value:
            return False
        if step_type == WorkflowStepType.CLEAN.value and not cleaned_artifact_present(latest):
            return False
        if step_type == WorkflowStepType.FINALIZE.value:
            if session.get("status") == "ready" and session.get("output_file"):
                return True
        stored = latest.get("input") or {}
        # Phase 4.5: missing fingerprint ⇒ non-reusable (safe rerun).
        if not has_input_fingerprint(stored):
            return False
        fp = build_step_fingerprint(
            step_type,
            session=session,
            dataset_key=self._context.get("dataset_key")
            or ((latest.get("output") or {}).get("artifacts") or {}).get("dataset_key"),
            cleaning_profile=session.get("cleaning_profile"),
        )
        return fingerprints_match(stored, fp)

    def _hydrate_context_from_output(
        self,
        step_type: str,
        output: Mapping[str, Any],
    ) -> None:
        artifacts = (output or {}).get("artifacts") or {}
        if artifacts.get("dataset_key"):
            self._context["dataset_key"] = artifacts["dataset_key"]
        if artifacts.get("cleaned_artifact_key"):
            self._context["cleaned_artifact_key"] = artifacts["cleaned_artifact_key"]
        if step_type == WorkflowStepType.PREPARE.value and artifacts.get("dataset_key"):
            self._context["dataset_key"] = artifacts["dataset_key"]

    def _dispatch_runner(
        self,
        step: str,
        user_id: str,
        session_id: str,
        session: Mapping[str, Any],
    ):
        if step == WorkflowStepType.INSPECT.value:
            return runners.run_inspect_step(user_id=user_id, session=session)
        if step == WorkflowStepType.PREPARE.value:
            result = runners.run_prepare_step(
                user_id=user_id, session_id=session_id, session=session
            )
            if result.artifacts.get("dataset_key"):
                self._context["dataset_key"] = result.artifacts["dataset_key"]
            return result
        if step == WorkflowStepType.MAP.value:
            return runners.run_map_step(session=session)
        if step == WorkflowStepType.VALIDATE.value:
            return runners.run_validate_step(session=session)
        if step == WorkflowStepType.CLEAN.value:
            return runners.run_clean_step(
                user_id=user_id,
                session_id=session_id,
                session=session,
                context=self._context,
                client=self.client,
            )
        if step == WorkflowStepType.FINALIZE.value:
            if not self._context.get("dataset_key"):
                prep = get_latest_step(
                    session_id, WorkflowStepType.PREPARE, client=self.client
                ) or {}
                self._hydrate_context_from_output(
                    WorkflowStepType.PREPARE.value, prep.get("output") or {}
                )
            if not self._context.get("cleaned_artifact_key"):
                clean = get_latest_step(
                    session_id, WorkflowStepType.CLEAN, client=self.client
                ) or {}
                self._hydrate_context_from_output(
                    WorkflowStepType.CLEAN.value, clean.get("output") or {}
                )
            if (
                not self._context.get("cleaned_handle")
                and self._context.get("cleaned_artifact_key")
            ):
                from app.services.workflow.artifacts import load_cleaned_artifact

                self._context["cleaned_handle"] = load_cleaned_artifact(
                    user_id, str(self._context["cleaned_artifact_key"])
                )
            if (
                not self._context.get("cleaned_handle")
                and self._context.get("cleaned_artifact_key")
            ):
                # A completed clean step is not authoritative if its private
                # artifact has been removed.  Rebuild it from the original
                # source, persist a new version, then continue finalization.
                clean = get_latest_step(
                    session_id, WorkflowStepType.CLEAN, client=self.client
                ) or {}
                if clean and is_reusable(clean):
                    mark_step_stale(
                        str(clean["id"]),
                        reason="Cleaned artifact missing from storage; rebuilding from source",
                        client=self.client,
                    )
                self._context.pop("cleaned_artifact_key", None)
                rebuilt = self.execute_step(
                    session_id,
                    WorkflowStepType.CLEAN.value,
                    user_id=user_id,
                    session=session,
                    force_new_version=True,
                )
                if rebuilt.status != "completed" or not self._context.get("cleaned_handle"):
                    raise RuntimeError("Could not rebuild missing cleaned artifact")
                logger.warning(
                    "cleaned_artifact_rebuilt_before_finalize",
                    extra={"session_id": session_id, "step_type": "clean"},
                )
            return runners.run_finalize_step(
                user_id=user_id,
                session=session,
                context=self._context,
                client=self.client,
            )
        raise UnknownStepError(step)


def get_workflow_engine(client: Any | None = None) -> WorkflowEngine:
    return WorkflowEngine(client=client)
