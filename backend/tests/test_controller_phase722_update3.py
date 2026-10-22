"""Phase 7.2.2-update3 — resolved decision retirement + option preservation."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.services.orchestrator.answer_apply import (
    apply_decision_answer,
    build_active_decision_payload,
    validate_active_decision_completeness,
)
from app.services.orchestrator.decision_identity import is_decision_confirmed, record_confirmed_decision
from app.services.orchestrator.ui_payload import build_orchestration_ui_payload, _session_active_decision
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


ROW_GRAIN_OPTIONS = [
    {"id": "invoice_line", "label": "ใช่ — รายการในบิล", "value": "invoice_line"},
    {"id": "invoice", "label": "ไม่ใช่ — ทั้งบิล", "value": "invoice"},
    {"id": "other", "label": "อย่างอื่น", "value": "other"},
]


def test_resolver_skips_confirmed_row_grain():
    session = _session(
        cleaning_recipe={"data_contract": {"row_grain": "invoice_line"}},
        processing_progress={
            "confirmed_decisions": {
                "row_grain": {
                    "value": "invoice_line",
                    "source": "user_confirmed",
                    "fingerprint": "abc",
                    "version": 1,
                },
            },
        },
    )
    keys = {d.decision_key for d in resolve_unresolved_decisions(session)}
    assert "row_grain" not in keys


def test_resolver_repairs_initial_prompt_captured_as_primary_metric():
    prompt = "วิเคราะห์ข้อมูลที่เลือกและสร้างรายงาน Visualization แบบกระชับ"
    session = _session(
        original_prompt=prompt,
        cleaning_recipe={
            "data_contract": {
                "row_grain": "source_record",
                "metric_definition": prompt,
                "business_purpose": "sales",
                "data_owner": "current_user",
                "period_status": "complete",
            }
        },
        processing_progress={
            "confirmed_decisions": {
                "primary_metric": {
                    "value": prompt,
                    "source": "user_confirmed",
                },
            },
        },
    )

    assert is_decision_confirmed(session, "primary_metric") is False
    decisions = resolve_unresolved_decisions(session)
    assert any(item.decision_key == "primary_metric" for item in decisions)


def test_apply_decision_retires_active_decision():
    store = {"data_setup_sessions": [_session(
        processing_progress={
            "active_decision": build_active_decision_payload(
                decision_key="row_grain",
                question="grain?",
                options=ROW_GRAIN_OPTIONS,
                expected_input="option_or_text",
            ),
        },
    )]}

    class _Q:
        def __init__(self, table, payload=None, filters=None):
            self.table = table
            self.payload = payload or {}
            self.filters = dict(filters or {})

        def update(self, payload):
            self.payload = payload
            return self

        def eq(self, k, v):
            self.filters[k] = v
            return self

        def execute(self):
            rows = store.setdefault(self.table, [])
            for row in rows:
                if all(row.get(k) == v for k, v in self.filters.items()):
                    if "cleaning_recipe" in self.payload:
                        row["cleaning_recipe"] = self.payload["cleaning_recipe"]
                    if "processing_progress" in self.payload:
                        row["processing_progress"] = self.payload["processing_progress"]
            return SimpleNamespace(data=rows)

    class _Client:
        def table(self, name):
            return _Q(name)

    session = store["data_setup_sessions"][0]
    updated, stamp = apply_decision_answer(
        _Client(),
        session_id="sess-1",
        user_id="user-1",
        session=session,
        decision_key="row_grain",
        context_updates={"row_grain": "invoice_line"},
        value="invoice_line",
    )
    progress = updated.get("processing_progress") or {}
    assert progress.get("active_decision") is None
    assert progress.get("resolved_decision_key") == "row_grain"
    assert is_decision_confirmed(updated, "row_grain")
    assert stamp is not None


def test_next_decision_after_row_grain_is_primary_metric():
    session = _session(
        cleaning_recipe={"data_contract": {"row_grain": "invoice_line"}},
        processing_progress={
            "confirmed_decisions": {
                "row_grain": {
                    "value": "invoice_line",
                    "source": "user_confirmed",
                },
            },
        },
    )
    one = select_one_decision(resolve_unresolved_decisions(session))
    assert one is not None
    assert one.decision_key == "primary_metric"


def test_options_persist_through_ui_payload_and_session_active_decision():
    active = build_active_decision_payload(
        decision_key="row_grain",
        question="ข้อมูล 1 แถวคือสินค้า 1 รายการในแต่ละบิลใช่ไหม?",
        options=ROW_GRAIN_OPTIONS,
        expected_input="option_or_text",
    )
    session = _session(
        processing_progress={"active_decision": active},
    )
    surfaced = _session_active_decision(session)
    assert surfaced is not None
    assert len(surfaced["options"]) == 3
    assert surfaced["options"][0]["id"] == "invoice_line"

    from app.services.orchestrator.decision_models import OrchestratorResult, AskUserDecision

    ask = AskUserDecision(
        question=active["question"],
        reason="contract_missing:row_grain_recorded",
        context_key="row_grain",
        decision_key="row_grain",
        options=[],
    )
    result = OrchestratorResult(
        decision=ask,
        assistant_message=active["question"],
        workflow_plan={"session_id": "sess-1", "status": "awaiting_answers", "steps": []},
    )
    payload = build_orchestration_ui_payload(result, session=session)
    assert payload["active_decision"]["options"][0]["label"] == "ใช่ — รายการในบิล"
    assert payload["awaiting_user"]["options"][0]["id"] == "invoice_line"


def test_refresh_after_resolution_clears_awaiting():
    from app.services.orchestrator.decision_models import OrchestratorResult, RespondDecision

    result = OrchestratorResult(
        decision=RespondDecision(message="saved"),
        assistant_message="saved",
        awaiting_user={
            "decision_key": "row_grain",
            "question": "stale",
            "options": ROW_GRAIN_OPTIONS,
        },
        workflow_plan={
            "session_id": "sess-1",
            "status": "processing",
            "awaiting_user": {"question": "stale plan question", "options": []},
            "steps": [],
        },
    )
    payload = build_orchestration_ui_payload(
        result,
        session={
            "id": "sess-1",
            "status": "processing",
            "processing_progress": {
                "resolved_decision_key": "row_grain",
                "confirmed_decisions": {
                    "row_grain": {
                        "value": "invoice_line",
                        "source": "user_confirmed",
                    },
                },
            },
            "cleaning_recipe": {"data_contract": {"row_grain": "invoice_line"}},
        },
    )
    assert payload["active_decision"] is None
    assert payload["awaiting_user"] is None
    assert payload["resolved_decision_key"] == "row_grain"


def test_single_choice_empty_options_incomplete():
    bad = {
        "decision_key": "row_grain",
        "status": "pending",
        "question": "grain?",
        "options": [],
        "expected_input": "single_choice",
        "free_text_allowed": False,
    }
    ok, err = validate_active_decision_completeness(bad)
    assert ok is False
    assert err == "missing_options_for_single_choice"


def test_collect_applies_even_when_plan_awaiting_user(
    monkeypatch, inline_asyncio_to_thread
):
    from app.services.orchestrator.orchestrator import WorkflowOrchestrator

    active = build_active_decision_payload(
        decision_key="row_grain",
        question="grain?",
        options=ROW_GRAIN_OPTIONS,
        expected_input="option_or_text",
    )
    store = {"data_setup_sessions": [_session(
        processing_progress={"active_decision": active},
    )]}

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

    async def no_llm(*_a, **_k):
        from app.services.orchestrator.decision_models import RespondDecision
        return RespondDecision(message="done"), "mock", []

    monkeypatch.setattr(orch, "_llm_decide", no_llm)
    monkeypatch.setattr(
        orch.engine,
        "get_workflow_plan",
        lambda *a, **k: {
            "session_id": "sess-1",
            "status": "awaiting_answers",
            "current_step": "validate",
            "next_action": {"action": "execute", "step_type": "validate"},
            "awaiting_user": {
                "reason_code": "VALIDATE_CONFIRM",
                "question": "approve validate?",
                "options": [{"id": "yes", "label": "yes"}],
            },
            "steps": [{"step_type": "validate", "status": "pending"}],
        },
    )

    result = asyncio.run(orch.handle_message(
        session_id="sess-1",
        user_id="user-1",
        message="invoice_line",
        orchestration_resolution={
            "decision_key": "row_grain",
            "value": "invoice_line",
        },
        tier="free",
    ))
    progress = store["data_setup_sessions"][0].get("processing_progress") or {}
    assert progress.get("resolved_decision_key") == "row_grain"
    assert (progress.get("active_decision") or {}).get("decision_key") != "row_grain"
    assert result.decision.type != "ask_user" or result.decision.decision_key != "row_grain"


def test_record_confirmed_decision_increments_version():
    session = _session()
    progress = record_confirmed_decision(
        {},
        session=session,
        decision_key="row_grain",
        value="invoice_line",
    )
    progress2 = record_confirmed_decision(
        progress,
        session=session,
        decision_key="row_grain",
        value="invoice",
    )
    assert progress2["confirmed_decisions"]["row_grain"]["version"] == 2


def test_repairs_awaiting_session_without_active_question():
    """Regression: action-limit/resume must not leave a phantom awaiting state."""
    from app.services.orchestrator.orchestrator import repair_missing_active_decision

    session = _session(
        cleaning_recipe={"data_contract": {"row_grain": "invoice_line"}},
        processing_progress={
            "resolved_decision_key": "row_grain",
            "confirmed_decisions": {
                "row_grain": {
                    "value": "invoice_line",
                    "source": "user_confirmed",
                },
            },
        },
    )
    store = {"data_setup_sessions": [session]}

    class _Q:
        def __init__(self, table, payload=None, filters=None):
            self.table = table
            self.payload = payload or {}
            self.filters = dict(filters or {})

        def update(self, payload):
            self.payload = payload
            return self

        def eq(self, key, value):
            self.filters[key] = value
            return self

        def execute(self):
            rows = store.setdefault(self.table, [])
            for row in rows:
                if all(row.get(k) == v for k, v in self.filters.items()):
                    row.update(self.payload)
            return SimpleNamespace(data=[dict(row) for row in rows])

    class _Client:
        def table(self, name):
            return _Q(name)

    repaired, ask = repair_missing_active_decision(
        _Client(),
        session_id="sess-1",
        user_id="user-1",
        session=session,
        step_type="validate",
    )

    active = (repaired.get("processing_progress") or {}).get("active_decision")
    assert ask is not None
    assert ask.decision_key == "primary_metric"
    assert active["decision_key"] == "primary_metric"
    assert active["question"]
    assert active["status"] == "pending"

    # A repeated resume keeps the same authoritative question.
    repaired_again, second_ask = repair_missing_active_decision(
        _Client(),
        session_id="sess-1",
        user_id="user-1",
        session=repaired,
        step_type="validate",
    )
    assert second_ask is None
    assert repaired_again["processing_progress"]["active_decision"] == active


def test_resume_replaces_later_question_when_primary_metric_captured_prompt():
    from app.services.orchestrator.orchestrator import repair_missing_active_decision

    prompt = "วิเคราะห์ข้อมูลที่เลือกและสร้างรายงาน Visualization แบบกระชับ"
    owner_active = build_active_decision_payload(
        decision_key="data_owner",
        question="ใครเป็นเจ้าของข้อมูลชุดนี้?",
        options=[],
        expected_input="free_text",
    )
    session = _session(
        original_prompt=prompt,
        cleaning_recipe={
            "data_contract": {
                "row_grain": "source_record",
                "metric_definition": prompt,
                "period_status": "complete",
                "business_purpose": "sales",
            }
        },
        processing_progress={
            "active_decision": owner_active,
            "confirmed_decisions": {
                "primary_metric": {"value": prompt, "source": "user_confirmed"},
            },
        },
    )
    store = {"data_setup_sessions": [session]}

    class _Q:
        def __init__(self, table, payload=None, filters=None):
            self.table = table
            self.payload = payload or {}
            self.filters = dict(filters or {})

        def update(self, payload):
            self.payload = payload
            return self

        def eq(self, key, value):
            self.filters[key] = value
            return self

        def execute(self):
            rows = store.setdefault(self.table, [])
            for row in rows:
                if all(row.get(k) == v for k, v in self.filters.items()):
                    row.update(self.payload)
            return SimpleNamespace(data=[dict(row) for row in rows])

    class _Client:
        def table(self, name):
            return _Q(name)

    repaired, ask = repair_missing_active_decision(
        _Client(),
        session_id="sess-1",
        user_id="user-1",
        session=session,
        step_type="validate",
    )
    active = repaired["processing_progress"]["active_decision"]
    assert ask is not None
    assert ask.decision_key == "primary_metric"
    assert active["decision_key"] == "primary_metric"


def test_resume_upgrades_legacy_owner_free_text_question_with_shortcut():
    from app.services.orchestrator.orchestrator import repair_missing_active_decision

    owner_active = build_active_decision_payload(
        decision_key="data_owner",
        question="ใครเป็นเจ้าของข้อมูลชุดนี้?",
        options=[],
        expected_input="free_text",
    )
    session = _session(
        cleaning_recipe={
            "data_contract": {
                "row_grain": "source_record",
                "metric_definition": "amount",
                "period_status": "complete",
                "business_purpose": "sales",
            }
        },
        processing_progress={"active_decision": owner_active},
    )
    store = {"data_setup_sessions": [session]}

    class _Q:
        def __init__(self, table, payload=None, filters=None):
            self.table = table
            self.payload = payload or {}
            self.filters = dict(filters or {})

        def update(self, payload):
            self.payload = payload
            return self

        def eq(self, key, value):
            self.filters[key] = value
            return self

        def execute(self):
            rows = store.setdefault(self.table, [])
            for row in rows:
                if all(row.get(k) == v for k, v in self.filters.items()):
                    row.update(self.payload)
            return SimpleNamespace(data=[dict(row) for row in rows])

    class _Client:
        def table(self, name):
            return _Q(name)

    repaired, ask = repair_missing_active_decision(
        _Client(),
        session_id="sess-1",
        user_id="user-1",
        session=session,
        step_type="validate",
    )
    active = repaired["processing_progress"]["active_decision"]
    assert ask is not None
    assert active["expected_input"] == "option_or_text"
    assert active["options"][0]["value"] == "current_user"
