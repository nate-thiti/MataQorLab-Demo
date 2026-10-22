"""Phase 7.2 — toolbox controller, unresolved decisions, stamps."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.services.orchestrator.answer_apply import parse_simple_answer
from app.services.orchestrator.capabilities import build_capability_catalog
from app.services.orchestrator.stamps import build_decision_stamp, merge_stamps_idempotent
from app.services.orchestrator.unresolved import (
    resolve_unresolved_decisions,
    select_one_decision,
    strip_raw_validator_checklist,
)
from app.services.orchestrator.working_memory import build_working_memory
from app.services.orchestrator.external_adapter import web_search_eligibility
from app.services.orchestrator.analytics_adapter import describe_analytics_route


def _session(**kwargs):
    base = {
        "id": "sess-1",
        "user_id": "user-1",
        "status": "awaiting_answers",
        "source_type": "file",
        "source_ref": {"file_name": "sales.xlsx"},
        "scan_result": {
            "row_count": 1000,
            "column_count": 11,
            "columns": [
                {"name": "invoice_no"},
                {"name": "product_code"},
                {"name": "amount"},
            ],
            "negative_value_count": 64,
        },
        "column_mapping": {},
        "cleaning_recipe": {"data_contract": {}},
        "processing_progress": {},
    }
    base.update(kwargs)
    return base


def test_setup_capabilities_available_analytics_not():
    caps = build_capability_catalog(
        session=_session(),
        workflow_plan={
            "next_action": {"action": "execute", "step_type": "inspect"},
            "steps": [{"step_type": "inspect", "status": "pending"}],
        },
        user_tier="free",
    )
    by_id = {c.capability_id: c for c in caps}
    assert by_id["inspect"].available is True
    assert by_id["query_data"].available is False
    assert by_id["query_data"].unavailable_reason == "dataset_not_ready"
    assert by_id["web_search"].available is False


def test_ready_does_not_advertise_analytics_to_setup_controller():
    caps = build_capability_catalog(
        session=_session(status="ready"),
        workflow_plan={"status": "ready", "steps": []},
        user_tier="plus",
        user_question="ยอดขายรวมเท่าไหร่",
    )
    by_id = {c.capability_id: c for c in caps}
    assert by_id["inspect"].available is False
    assert by_id["query_data"].available is False
    assert by_id["query_data"].unavailable_reason == "handled_by_analysis_agent"
    assert by_id["calculate_metrics"].available is False
    assert by_id["calculate_metrics"].unavailable_reason == "handled_by_analysis_agent"
    assert by_id["web_search"].available is False
    assert by_id["web_search"].unavailable_reason == "handled_by_analysis_agent"


def test_web_search_tier_gate():
    free = web_search_eligibility(
        user_tier="free",
        user_question="ราคา USD THB วันนี้",
        session_ready=True,
    )
    plus = web_search_eligibility(
        user_tier="plus",
        user_question="ราคา USD THB วันนี้",
        session_ready=True,
    )
    assert free["available"] is False
    assert free["unavailable_reason"] == "plan_not_eligible"
    assert plus["available"] is True


def test_web_search_available_without_keyword_match():
    """Model may choose web_search from context even if keywords are absent."""
    plus = web_search_eligibility(
        user_tier="plus",
        user_question="ช่วยหาบริบทตลาดเพิ่มให้รายงานนี้",
        session_ready=True,
    )
    assert plus["available"] is True


def test_bulk_missing_fields_become_one_decision():
    session = _session(
        cleaning_recipe={"data_contract": {}},
        column_mapping={"amount": "sales"},
    )
    decisions = resolve_unresolved_decisions(session)
    one = select_one_decision(decisions)
    assert one is not None
    assert one.decision_key in {
        "row_grain",
        "return_policy",
        "primary_metric",
        "business_purpose",
        "data_owner",
        "reporting_period_status",
        "mapping_confirmed",
        "business_context_reviewed",
    }
    # Must not be a multi-field dump
    assert "data_owner" not in (one.question_th or "") or one.decision_key == "data_owner"
    assert select_one_decision(decisions).decision_key == one.decision_key


def test_strip_raw_validator_checklist():
    assert strip_raw_validator_checklist(
        "Please provide missing contract details: owner, grain, metric"
    ) == ""
    assert strip_raw_validator_checklist("ข้อมูล 1 แถวคือรายการในบิลใช่ไหม?") != ""


def test_confirmed_context_excludes_reask():
    session = _session(
        cleaning_recipe={
            "data_contract": {
                "row_grain": "invoice_line",
                "business_purpose": "sales_analysis",
                "metric_definition": "sales",
                "data_owner": "ops",
                "period_status": "complete",
                "mapping_confirmed": True,
                "business_context_reviewed": True,
                "return_policy": {"value": "negative_is_return", "source": "user_confirmed"},
            }
        },
        column_mapping={"amount": "sales", "invoice_no": "invoice", "product_code": "product"},
    )
    decisions = resolve_unresolved_decisions(session)
    keys = {d.decision_key for d in decisions}
    assert "row_grain" not in keys
    assert "return_policy" not in keys


def test_parse_yes_for_row_grain():
    value, updates = parse_simple_answer("ใช่", decision_key="row_grain", options=[])
    assert value == "invoice_line"
    assert updates["row_grain"] == "invoice_line"


def test_decision_stamp_idempotent():
    a = build_decision_stamp(
        session_id="sess-1", decision_key="row_grain", value="invoice_line"
    )
    b = build_decision_stamp(
        session_id="sess-1", decision_key="row_grain", value="invoice_line"
    )
    assert a.stamp_id == b.stamp_id
    merged = merge_stamps_idempotent([], [a, b])
    assert len(merged) == 1


def test_working_memory_mode_switch():
    setup_mem = build_working_memory(session=_session(), workflow_plan={"status": "awaiting_answers"})
    ready_mem = build_working_memory(
        session=_session(status="ready"),
        workflow_plan={"status": "ready"},
        include_contract_decisions=False,
    )
    assert setup_mem.mode == "setup"
    assert ready_mem.mode == "analysis"
    assert not any(
        c.get("capability_id") == "query_data" and c.get("available")
        for c in ready_mem.available_capabilities
    )
    assert any(
        c.get("capability_id") == "query_data"
        and c.get("unavailable_reason") == "handled_by_analysis_agent"
        for c in ready_mem.available_capabilities
    )


def test_analytics_adapter_forbids_arbitrary_sql():
    route = describe_analytics_route("query_data")
    assert route["allows_arbitrary_sql_from_ai"] is False
    assert "question_analytics" in route["authority"]


def test_controller_asks_one_question_not_checklist(
    monkeypatch, inline_asyncio_to_thread
):
    from app.services.orchestrator.orchestrator import WorkflowOrchestrator
    from app.services.orchestrator.decision_models import RespondDecision

    store = {
        "data_setup_sessions": [_session(
            column_mapping={"amount": "sales"},
            cleaning_recipe={"data_contract": {}},
        )],
        "workflow_steps": [],
    }

    class _Q:
        def __init__(self, table, payload=None, filters=None):
            self.table = table
            self.payload = payload or {}
            self.filters = dict(filters or {})
            self._op = "select"

        def select(self, *_a, **_k):
            self._op = "select"
            return self

        def update(self, payload):
            self._op = "update"
            self.payload = payload
            return self

        def eq(self, k, v):
            self.filters[k] = v
            return self

        def limit(self, n):
            self._limit = n
            return self

        def execute(self):
            rows = store.setdefault(self.table, [])
            if self._op == "update":
                for row in rows:
                    if all(row.get(k) == v for k, v in self.filters.items()):
                        row.update(self.payload)
                return SimpleNamespace(data=rows)
            matched = [r for r in rows if all(r.get(k) == v for k, v in self.filters.items())]
            return SimpleNamespace(data=[dict(r) for r in matched[: getattr(self, "_limit", 99)]])

    class _Client:
        def table(self, name):
            return _Q(name)

    orch = WorkflowOrchestrator(client=_Client(), llm=SimpleNamespace())

    async def no_llm(*_a, **_k):
        # If collect path works, LLM should not be needed for validate-next.
        return RespondDecision(message="should-not-leak-checklist"), "mock", []

    monkeypatch.setattr(orch, "_llm_decide", no_llm)
    monkeypatch.setattr(
        orch.engine,
        "get_workflow_plan",
        lambda *a, **k: {
            "session_id": "sess-1",
            "status": "awaiting_answers",
            "current_step": "validate",
            "next_action": {"action": "execute", "step_type": "validate"},
            "steps": [
                {"step_type": "inspect", "status": "completed"},
                {"step_type": "prepare", "status": "completed"},
                {"step_type": "validate", "status": "pending"},
            ],
            "awaiting_user": None,
        },
    )

    result = asyncio.run(orch.handle_message(
        session_id="sess-1",
        user_id="user-1",
        message="ช่วยเตรียมข้อมูล",
        settlement_key="p72-one-q",
    ))
    assert result.decision.type == "ask_user"
    q = result.assistant_message.lower()
    assert "please provide" not in q
    assert "data_owner_recorded" not in q
    assert result.awaiting_user.get("decision_key")
    # Active decision persisted
    progress = store["data_setup_sessions"][0].get("processing_progress") or {}
    assert (progress.get("active_decision") or {}).get("decision_key")
