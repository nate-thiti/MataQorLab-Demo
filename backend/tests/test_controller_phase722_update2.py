"""Phase 7.2.2-update2 — active_decision contract + validator alignment."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.services.orchestrator.answer_apply import (
    build_active_decision_payload,
    validate_active_decision_completeness,
)
from app.services.orchestrator.ui_payload import build_orchestration_ui_payload
from app.services.orchestrator.unresolved import resolve_unresolved_decisions, select_one_decision


def _session(**kwargs):
    base = {
        "id": "sess-1",
        "user_id": "user-1",
        "status": "awaiting_answers",
        "source_type": "file",
        "source_ref": {"file_name": "sales.xlsx"},
        "scan_result": {
            "row_count": 1000,
            "columns": [
                {"name": "invoice_no"},
                {"name": "product_code"},
                {"name": "amount"},
            ],
            "negative_value_count": 0,
        },
        "column_mapping": {"amount": "sales"},
        "cleaning_recipe": {"data_contract": {}},
        "processing_progress": {},
    }
    base.update(kwargs)
    return base


def test_validate_missing_row_grain_not_validate_approval():
    one = select_one_decision(resolve_unresolved_decisions(_session()))
    assert one is not None
    assert one.decision_key == "row_grain"
    assert "แถว" in (one.question_th or "")
    assert "อนุมัติ validate" not in (one.question_th or "").lower()
    assert "approve validate" not in (one.question_th or "").lower()
    assert len(one.options) >= 2


def test_questions_use_detected_inventory_schema_instead_of_sales_template():
    session = _session(
        scan_result={
            "row_count": 420,
            "suggested_domain": "inventory",
            "domain_options": [
                {"value": "inventory", "label": "Inventory", "recommended": True},
                {"value": "manufacturing", "label": "Manufacturing"},
            ],
            "grain_options": [
                {"value": "inventory_snapshot", "label": "One inventory snapshot record"},
                {"value": "source_record", "label": "One source record"},
            ],
            "columns": [
                {"name": "SnapshotDate", "inferred_type": "date", "suggested_role": "date"},
                {"name": "Warehouse", "inferred_type": "category", "suggested_role": "warehouse"},
                {"name": "StockOnHand", "inferred_type": "number", "suggested_role": "stock_level"},
            ],
        },
        column_mapping={"StockOnHand": "stock_level", "SnapshotDate": "date"},
        cleaning_recipe={"data_contract": {"row_grain": "inventory_snapshot"}},
        processing_progress={
            "confirmed_decisions": {
                "row_grain": {"value": "inventory_snapshot", "source": "user_confirmed"},
            },
        },
    )

    decisions = resolve_unresolved_decisions(session)
    metric = next(item for item in decisions if item.decision_key == "primary_metric")
    purpose = next(item for item in decisions if item.decision_key == "business_purpose")

    assert "StockOnHand" in (metric.question_th or "")
    assert any(option.get("value") == "StockOnHand" for option in metric.options)
    assert "ยอดขาย (Sales) ใช่ไหม" not in (metric.question_th or "")
    assert "สินค้าคงคลัง" in (purpose.question_th or "")
    assert purpose.options[0]["value"] == "inventory"


def test_row_grain_question_uses_scan_candidates_and_column_names():
    session = _session(
        scan_result={
            "columns": [
                {"name": "MovementId", "suggested_role": "line_id"},
                {"name": "Sku", "suggested_role": "product"},
            ],
            "grain_options": [
                {"value": "inventory_movement", "label": "One inventory movement"},
                {"value": "source_record", "label": "One source record"},
            ],
            "suggested_domain": "inventory",
        },
        column_mapping={"MovementId": "line_id", "Sku": "product"},
    )

    grain = next(
        item for item in resolve_unresolved_decisions(session)
        if item.decision_key == "row_grain"
    )

    assert "MovementId" in (grain.question_th or "")
    assert [option["value"] for option in grain.options][:2] == [
        "inventory_movement",
        "source_record",
    ]


def test_negative_inventory_values_are_not_assumed_to_be_sales_returns():
    session = _session(
        scan_result={
            "suggested_domain": "inventory",
            "negative_value_count": 17,
            "columns": [
                {"name": "StockChange", "inferred_type": "number", "suggested_role": "stock_out"},
            ],
        },
        column_mapping={"StockChange": "stock_out"},
    )

    policy = next(
        item for item in resolve_unresolved_decisions(session)
        if item.decision_key == "return_policy"
    )

    assert "StockChange" in (policy.question_th or "")
    assert "จ่าย/ตัดสต็อก" in (policy.question_th or "")
    assert "สินค้าคืนใช่ไหม" not in (policy.question_th or "")
    assert policy.options[0]["value"] == "negative_is_outflow"


def test_active_decision_completeness_contract():
    payload = build_active_decision_payload(
        decision_key="row_grain",
        question="ข้อมูล 1 แถวคือสินค้า 1 รายการในแต่ละบิลใช่ไหม?",
        options=[
            {"id": "invoice_line", "label": "ใช่ — รายการในบิล", "value": "invoice_line"},
            {"id": "invoice", "label": "ไม่ใช่ — ทั้งบิล", "value": "invoice"},
        ],
        expected_input="single_choice",
        free_text_allowed=True,
    )
    ok, err = validate_active_decision_completeness(payload)
    assert ok is True
    assert err is None
    assert payload["expected_input"] == "single_choice"
    assert payload["free_text_allowed"] is True


def test_no_options_requires_free_text():
    payload = build_active_decision_payload(
        decision_key="data_owner",
        question="ใครเป็นเจ้าของข้อมูลชุดนี้?",
        options=[],
        free_text_allowed=True,
    )
    ok, err = validate_active_decision_completeness(payload)
    assert ok is True

    bad = {
        "decision_key": "data_owner",
        "status": "pending",
        "question": "ใครเป็นเจ้าของข้อมูลชุดนี้?",
        "options": [],
        "expected_input": "free_text",
        "free_text_allowed": False,
    }
    ok2, err2 = validate_active_decision_completeness(bad)
    assert ok2 is False
    assert err2 == "no_input_mode"


def test_data_owner_question_offers_current_user_shortcut():
    session = _session(
        cleaning_recipe={
            "data_contract": {
                "row_grain": "source_record",
                "metric_definition": "amount",
                "period_status": "complete",
                "business_purpose": "sales",
            }
        },
    )
    owner = next(
        item for item in resolve_unresolved_decisions(session)
        if item.decision_key == "data_owner"
    )
    assert owner.options == [{
        "id": "current_user",
        "label": "ฉันเป็นเจ้าของข้อมูลชุดนี้",
        "value": "current_user",
    }]


def test_incomplete_active_decision_fail_closed_in_ui_payload():
    from app.services.orchestrator.decision_models import OrchestratorResult, RespondDecision

    result = OrchestratorResult(
        decision=RespondDecision(message="ok"),
        assistant_message="ok",
        workflow_plan={"session_id": "s1", "status": "awaiting_answers", "steps": []},
    )
    payload = build_orchestration_ui_payload(
        result,
        session={
            "id": "s1",
            "status": "awaiting_answers",
            "processing_progress": {
                "active_decision": {
                    "decision_key": "row_grain",
                    "status": "pending",
                    "question": "",
                    "options": [],
                    "free_text_allowed": False,
                },
            },
        },
    )
    assert payload["active_decision"] is None
    assert payload["incomplete_active_decision"] == "missing_question"
    assert payload["awaiting_user"] is None


def test_confirmation_required_validate_uses_unresolved_not_generic(
    monkeypatch, inline_asyncio_to_thread
):
    from app.services.orchestrator.orchestrator import WorkflowOrchestrator
    from app.services.workflow.engine import ConfirmationRequired
    from app.services.workflow.models import ConfirmationDecision

    store = {"data_setup_sessions": [_session()], "workflow_steps": []}

    class _Q:
        def __init__(self, table, payload=None, filters=None):
            self.table = table
            self.payload = payload or {}
            self.filters = dict(filters or {})

        def select(self, *_a, **_k):
            return self

        def update(self, payload):
            self.payload = payload
            return self

        def eq(self, k, v):
            self.filters[k] = v
            return self

        def limit(self, n):
            return self

        def execute(self):
            rows = store.setdefault(self.table, [])
            if self.payload:
                for row in rows:
                    if all(row.get(k) == v for k, v in self.filters.items()):
                        row.update(self.payload)
            matched = [r for r in rows if all(r.get(k) == v for k, v in self.filters.items())]
            return SimpleNamespace(data=[dict(r) for r in matched])

    class _Client:
        def table(self, name):
            return _Q(name)

    orch = WorkflowOrchestrator(client=_Client(), llm=SimpleNamespace())

    async def boom(*_a, **_k):
        raise ConfirmationRequired(
            ConfirmationDecision(
                required=True,
                reason_code="BUSINESS_CONTRACT_CHANGE",
                reason="Business contract change requires confirmation.",
                context={},
                confirmation_fingerprint="fp1",
            ),
            step_type="validate",
        )

    monkeypatch.setattr(orch.engine, "execute_step", boom)
    monkeypatch.setattr(
        orch.engine,
        "get_workflow_plan",
        lambda *a, **k: {
            "session_id": "sess-1",
            "status": "awaiting_answers",
            "next_action": {"action": "execute", "step_type": "validate"},
            "steps": [{"step_type": "validate", "status": "pending"}],
        },
    )

    result = asyncio.run(orch.handle_message(
        session_id="sess-1",
        user_id="user-1",
        message="ดำเนินการต่อ",
        tier="free",
    ))
    assert result.decision.type == "ask_user"
    assert result.decision.decision_key == "row_grain"
    assert "แถว" in result.assistant_message
    progress = store["data_setup_sessions"][0].get("processing_progress") or {}
    ad = progress.get("active_decision") or {}
    assert ad.get("decision_key") == "row_grain"
    assert ad.get("question")
    assert ad.get("options")
