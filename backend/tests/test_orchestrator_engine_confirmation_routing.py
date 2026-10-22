"""Engine confirmation must not be swallowed by collect_input."""
from __future__ import annotations

from app.services.orchestrator.orchestrator import (
    _is_engine_confirmation_decision,
    _should_skip_collect_for_engine_resolution,
    _structured_engine_decision,
)


def test_cleaning_confirmation_is_engine_decision():
    assert _is_engine_confirmation_decision(
        {"decision_key": "cleaning_confirmation", "reason_code": "AGGRESSIVE_CLEANING"},
        "cleaning_confirmation",
    )


def test_row_grain_is_not_engine_decision():
    assert not _is_engine_confirmation_decision(
        {"decision_key": "row_grain", "reason_code": "MISSING_ROW_GRAIN"},
        "row_grain",
    )


def test_skip_collect_for_approve_click_on_cleaning_confirmation():
    assert _should_skip_collect_for_engine_resolution(
        active={
            "decision_key": "cleaning_confirmation",
            "reason_code": "AGGRESSIVE_CLEANING",
        },
        collect_key="cleaning_confirmation",
        awaiting={"step_type": "clean", "reason_code": "AGGRESSIVE_CLEANING"},
        orchestration_resolution={
            "decision": "approved",
            "value": "approve",
            "decision_key": "cleaning_confirmation",
        },
    )


def test_do_not_skip_collect_for_row_grain_option():
    assert not _should_skip_collect_for_engine_resolution(
        active={"decision_key": "row_grain"},
        collect_key="row_grain",
        awaiting=None,
        orchestration_resolution={
            "value": "invoice_line",
            "decision_key": "row_grain",
        },
    )


def test_business_context_reviewed_is_never_engine_confirmation():
    assert not _is_engine_confirmation_decision(
        {
            "decision_key": "business_context_reviewed",
            "reason_code": "BUSINESS_CONTRACT_CHANGE",
        },
        "business_context_reviewed",
    )
    assert not _should_skip_collect_for_engine_resolution(
        active={
            "decision_key": "business_context_reviewed",
            "reason_code": "BUSINESS_CONTRACT_CHANGE",
        },
        collect_key="business_context_reviewed",
        awaiting={"step_type": "validate"},
        orchestration_resolution={
            "decision": "approved",
            "value": "approve",
            "decision_key": "business_context_reviewed",
        },
    )


def test_mapping_confirmed_stays_on_collect_path():
    assert not _is_engine_confirmation_decision(
        {"decision_key": "mapping_confirmed", "reason_code": "AMBIGUOUS_MAPPING"},
        "mapping_confirmed",
    )


def test_clean_confirmation_skips_collect_even_with_contract_active_key():
    assert _should_skip_collect_for_engine_resolution(
        active={
            "decision_key": "business_context_reviewed",
            "reason_code": "BUSINESS_CONTRACT_CHANGE",
        },
        collect_key="business_context_reviewed",
        awaiting={"step_type": "clean", "reason_code": "AGGRESSIVE_CLEANING"},
        orchestration_resolution={
            "decision": "modified",
            "value": "modify",
            "decision_key": "cleaning_confirmation",
        },
    )


def test_structured_engine_decision_from_value():
    assert _structured_engine_decision({"value": "modify"}) == "modified"
    assert _structured_engine_decision({"decision": "approve"}) == "approved"
    assert _structured_engine_decision({"value": "invoice_line"}) is None


def test_plan_has_executable_next_for_finalize_retry():
    from app.services.orchestrator.orchestrator import WorkflowOrchestrator

    assert WorkflowOrchestrator._plan_has_executable_next({
        "next_action": {"action": "retry", "step_type": "finalize"},
        "awaiting_user": None,
    })
    assert not WorkflowOrchestrator._plan_has_executable_next({
        "next_action": {"action": "retry", "step_type": "finalize"},
        "awaiting_user": {"step_type": "finalize"},
    })


def test_deterministic_next_retries_failed_finalize_without_prior_tool():
    from app.services.orchestrator.orchestrator import WorkflowOrchestrator

    orch = WorkflowOrchestrator.__new__(WorkflowOrchestrator)
    decision = orch._deterministic_next_decision(
        workflow_ctx={
            "next_action": {
                "action": "retry",
                "step_type": "finalize",
                "reason": "Retry finalize after failure.",
            },
        },
        last_tool_summary=None,
        allow_after_tool=True,
    )
    assert decision is not None
    assert getattr(decision, "type", None) == "tool_call"
    assert getattr(decision, "step_type", None) == "finalize"
