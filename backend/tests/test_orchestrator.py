"""Phase 5 — orchestrator authority, awaiting_user, truthfulness."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.orchestrator.decision_models import ToolCallDecision
from app.services.orchestrator.orchestrator import WorkflowOrchestrator
from app.services.orchestrator.prompts import template_for_reason_code
from app.services.tools.types import ToolResult
from app.services.workflow.policies import (
    build_step_fingerprint,
    evaluate_confirmation_requirement,
)


class _Query:
    def __init__(self, store, table, payload=None, filters=None):
        self.store = store
        self.table_name = table
        self.payload = payload or {}
        self.filters = dict(filters or {})
        self._order = []
        self._limit = None
        self._op = "select"

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self.payload = payload
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def order(self, key, desc=False):
        self._order.append((key, desc))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        rows = self.store.setdefault(self.table_name, [])
        if self._op == "insert":
            row = {"id": f"{self.table_name}-{len(rows)+1}", **self.payload}
            rows.append(row)
            return SimpleNamespace(data=[row])
        if self._op == "update":
            updated = []
            for row in rows:
                if all(row.get(k) == v for k, v in self.filters.items()):
                    row.update(self.payload)
                    updated.append(dict(row))
            return SimpleNamespace(data=updated)
        matched = [
            row for row in rows
            if all(row.get(k) == v for k, v in self.filters.items())
        ]
        for key, desc in reversed(self._order):
            matched.sort(key=lambda r: r.get(key) or 0, reverse=desc)
        if self._limit is not None:
            matched = matched[: self._limit]
        return SimpleNamespace(data=[dict(r) for r in matched])


class _FakeClient:
    def __init__(self, session=None, steps=None):
        self.store = {
            "data_setup_sessions": [session or {
                "id": "sess-1",
                "user_id": "user-1",
                "status": "processing",
                "source_type": "file",
                "source_fingerprint": "src-v1",
                "column_mapping": {"a": "sales"},
                "cleaning_profile": "standard",
                "cleaning_recipe": {"data_contract": {"row_grain": "order"}},
                "source_ref": {"file_name": "sales.xlsx"},
                "scan_result": {"row_count": 100, "columns": [{"name": "a"}]},
            }],
            "workflow_steps": list(steps or []),
        }

    def table(self, name):
        return _Query(self.store, name)

    def rpc(self, *_a, **_k):
        class _Rpc:
            def execute(self_inner):
                raise RuntimeError("rpc unavailable")
        return _Rpc()


def _step(step_type, status, **extra):
    base = {
        "id": f"{step_type}-{status}",
        "data_setup_session_id": "sess-1",
        "step_type": step_type,
        "status": status,
        "version": 1,
        "attempt": 1,
        "input": {},
        "output": {},
    }
    base.update(extra)
    return base


def _orch(client):
    from app.services.workflow.engine import WorkflowEngine

    return WorkflowOrchestrator(
        client=client,
        engine=WorkflowEngine(client=client, skip_capability_check=True),
    )


def test_finalize_blocked_when_clean_incomplete(monkeypatch, inline_asyncio_to_thread):
    session = _FakeClient().store["data_setup_sessions"][0]
    fp = lambda step: build_step_fingerprint(step, session=session)
    steps = [
        _step("inspect", "completed", input=fp("inspect")),
        _step("prepare", "completed", input=fp("prepare"),
              output={"artifacts": {"dataset_key": "sales.xlsx"}}),
        _step("map", "completed", input=fp("map")),
        _step("validate", "completed", input=fp("validate")),
    ]
    client = _FakeClient(session=session, steps=steps)
    orch = _orch(client)
    called = {"finalize": 0}

    def boom_finalize(*_a, **_k):
        called["finalize"] += 1
        raise AssertionError("finalize must not run")

    monkeypatch.setattr("app.services.workflow.runners.run_finalize_step", boom_finalize)

    result = asyncio.run(orch.handle_message(
        session_id="sess-1",
        user_id="user-1",
        message="finalize now",
        llm_decision_override=ToolCallDecision(
            step_type="finalize", reason="ai wants finalize"
        ),
    ))
    assert called["finalize"] == 0
    assert result.decision.type == "respond"
    assert "finalize" in result.assistant_message.lower() or "ไม่" in result.assistant_message


def test_initial_setup_prompt_is_not_consumed_as_active_decision_answer(
    monkeypatch, inline_asyncio_to_thread
):
    from app.services.orchestrator.answer_apply import build_active_decision_payload

    prompt = "วิเคราะห์ข้อมูลที่เลือกและสร้างรายงาน Visualization แบบกระชับ"
    active = build_active_decision_payload(
        decision_key="primary_metric",
        question="ต้องการใช้คอลัมน์ใดเป็นตัวชี้วัดหลัก?",
        options=[{"id": "amount", "label": "ยอดขาย — amount", "value": "amount"}],
    )
    session = {
        "id": "sess-1",
        "user_id": "user-1",
        "status": "awaiting_answers",
        "source_type": "file",
        "source_fingerprint": "src-v1",
        "column_mapping": {"amount": "sales"},
        "cleaning_profile": "standard",
        "cleaning_recipe": {"data_contract": {"row_grain": "source_record"}},
        "source_ref": {"file_name": "sales.xlsx"},
        "scan_result": {
            "row_count": 1000,
            "columns": [{"name": "amount", "inferred_type": "number"}],
        },
        "processing_progress": {"active_decision": active},
    }
    client = _FakeClient(session=session)
    orch = _orch(client)
    monkeypatch.setattr(
        orch.engine,
        "get_workflow_plan",
        lambda *a, **k: {
            "session_id": "sess-1",
            "status": "awaiting_answers",
            "current_step": "validate",
            "next_action": {"action": "execute", "step_type": "validate"},
            "steps": [{"step_type": "validate", "status": "pending"}],
        },
    )

    result = asyncio.run(orch.handle_message(
        session_id="sess-1",
        user_id="user-1",
        message=prompt,
        setup_intent="prepare_attached_source_for_analysis",
    ))

    contract = client.store["data_setup_sessions"][0]["cleaning_recipe"]["data_contract"]
    assert "metric_definition" not in contract
    assert result.decision.type == "ask_user"
    assert result.decision.decision_key == "primary_metric"
    assert result.assistant_message == active["question"]
    assert result.audit["actions"][-1]["reason"] == "initial_prompt_not_consumed_as_answer"


def test_aggressive_clean_returns_question_not_execution(
    monkeypatch, inline_asyncio_to_thread
):
    session = {
        "id": "sess-1",
        "user_id": "user-1",
        "status": "processing",
        "source_type": "file",
        "source_fingerprint": "src-v1",
        "column_mapping": {"a": "sales"},
        "cleaning_profile": "aggressive",
        "cleaning_recipe": {"data_contract": {}},
        "source_ref": {"file_name": "sales.xlsx"},
        "scan_result": {"row_count": 10, "columns": [{"name": "a"}]},
    }
    fp = lambda step, **kw: build_step_fingerprint(step, session=session, **kw)
    steps = [
        _step("inspect", "completed", input=fp("inspect")),
        _step("prepare", "completed", input=fp("prepare"),
              output={"artifacts": {"dataset_key": "sales.xlsx"}}),
        _step("map", "completed", input=fp("map")),
        _step("validate", "completed", input=fp("validate")),
    ]
    client = _FakeClient(session=session, steps=steps)
    orch = _orch(client)
    orch.engine._context["dataset_key"] = "sales.xlsx"
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("clean must not run")

    monkeypatch.setattr("app.services.workflow.runners.run_clean_step", boom)
    result = asyncio.run(orch.handle_message(
        session_id="sess-1",
        user_id="user-1",
        message="clean please",
        llm_decision_override=ToolCallDecision(step_type="clean", reason="next"),
    ))
    assert called["n"] == 0
    assert result.decision.type == "ask_user"
    assert "Aggressive" in result.assistant_message or "aggressive" in (
        result.decision.reason or ""
    ).lower() or "AGGRESSIVE" in (result.decision.reason or "")


def test_user_approve_then_clean_runs(monkeypatch, inline_asyncio_to_thread):
    session = {
        "id": "sess-1",
        "user_id": "user-1",
        "status": "awaiting_answers",
        "source_type": "file",
        "source_fingerprint": "src-v1",
        "column_mapping": {"a": "sales"},
        "cleaning_profile": "aggressive",
        "cleaning_recipe": {"data_contract": {}},
        "source_ref": {"file_name": "sales.xlsx"},
        "scan_result": {},
    }
    proposed = build_step_fingerprint("clean", session=session, dataset_key="sales.xlsx")
    conf = evaluate_confirmation_requirement(session, "clean", proposed_input=proposed)
    steps = [
        _step("inspect", "completed", input=build_step_fingerprint("inspect", session=session)),
        _step("prepare", "completed", input=build_step_fingerprint("prepare", session=session),
              output={"artifacts": {"dataset_key": "sales.xlsx"}}),
        _step("map", "completed", input=build_step_fingerprint("map", session=session)),
        _step("validate", "completed", input=build_step_fingerprint("validate", session=session)),
        _step(
            "clean",
            "awaiting_user",
            input={
                **proposed,
                "confirmation_fingerprint": conf.confirmation_fingerprint,
                "reason_code": "AGGRESSIVE_CLEANING",
            },
            output={"metadata": {"reason_code": "AGGRESSIVE_CLEANING"}},
            requires_confirmation=True,
        ),
    ]
    client = _FakeClient(session=session, steps=steps)
    orch = _orch(client)
    orch.engine._context["dataset_key"] = "sales.xlsx"
    ran = {"n": 0}

    def fake_clean(*_a, **_k):
        ran["n"] += 1
        return ToolResult(
            tool="clean_data",
            status="completed",
            summary="Cleaning completed",
            artifacts={"cleaned_artifact_key": "c.parquet", "dataset_key": "sales.xlsx"},
            findings=[{"type": "duplicates_removed", "count": 2}],
        )

    monkeypatch.setattr("app.services.workflow.runners.run_clean_step", fake_clean)

    async def no_llm(*_a, **_k):
        from app.services.orchestrator.decision_models import RespondDecision

        return RespondDecision(message="Cleaning completed"), "mock", []

    monkeypatch.setattr(orch, "_llm_decide", no_llm)
    result = asyncio.run(orch.handle_message(
        session_id="sess-1",
        user_id="user-1",
        message="ทำเลย",
    ))
    assert ran["n"] == 1
    assert (
        "clean" in result.assistant_message.lower()
        or "เสร็จ" in result.assistant_message
        or "completed" in result.assistant_message.lower()
        or "finalize" in result.assistant_message.lower()
        or (result.engine_result or {}).get("step") in {"clean", "finalize"}
    )


def test_user_reject_never_runs_clean(monkeypatch, inline_asyncio_to_thread):
    session = {
        "id": "sess-1",
        "user_id": "user-1",
        "status": "awaiting_answers",
        "source_type": "file",
        "source_fingerprint": "src-v1",
        "column_mapping": {"a": "sales"},
        "cleaning_profile": "aggressive",
        "cleaning_recipe": {},
        "source_ref": {"file_name": "sales.xlsx"},
    }
    proposed = build_step_fingerprint(
        "clean", session=session, dataset_key="sales.xlsx"
    )
    conf = evaluate_confirmation_requirement(
        session, "clean", proposed_input=proposed
    )
    steps = [
        _step("inspect", "completed", input=build_step_fingerprint("inspect", session=session)),
        _step("prepare", "completed", input=build_step_fingerprint("prepare", session=session),
              output={"artifacts": {"dataset_key": "sales.xlsx"}}),
        _step(
            "clean",
            "awaiting_user",
            input={
                **proposed,
                "confirmation_fingerprint": conf.confirmation_fingerprint,
                "reason_code": "AGGRESSIVE_CLEANING",
            },
        ),
    ]
    client = _FakeClient(session=session, steps=steps)
    orch = _orch(client)
    orch.engine._context["dataset_key"] = "sales.xlsx"

    def boom(*_a, **_k):
        raise AssertionError("must not run")

    monkeypatch.setattr("app.services.workflow.runners.run_clean_step", boom)

    async def no_llm(*_a, **_k):
        from app.services.orchestrator.decision_models import RespondDecision

        return RespondDecision(message="should not reach llm"), "mock", []

    monkeypatch.setattr(orch, "_llm_decide", no_llm)
    result = asyncio.run(orch.handle_message(
        session_id="sess-1",
        user_id="user-1",
        message="ไม่เอา",
    ))
    assert result.decision.type == "respond"
    assert "ยกเลิก" in result.assistant_message or "clean" in result.assistant_message


def test_hallucinated_success_corrected_on_failed_tool(
    monkeypatch, inline_asyncio_to_thread
):
    session = _FakeClient().store["data_setup_sessions"][0]
    steps = [
        _step("inspect", "completed", input=build_step_fingerprint("inspect", session=session)),
    ]
    client = _FakeClient(session=session, steps=steps)
    orch = _orch(client)

    def fail_prepare(*_a, **_k):
        return ToolResult(tool="prepare_data", status="failed", summary="boom")

    monkeypatch.setattr("app.services.workflow.runners.run_prepare_step", fail_prepare)
    result = asyncio.run(orch.handle_message(
        session_id="sess-1",
        user_id="user-1",
        message="prepare",
        llm_decision_override=ToolCallDecision(step_type="prepare", reason="go"),
    ))
    assert result.decision.type == "respond"
    # Engine surfaces failure either as ToolResult failed or raised error text.
    assert (
        "ล้มเหลว" in result.assistant_message
        or "failed" in result.assistant_message.lower()
        or "boom" in result.assistant_message.lower()
        or "ไม่สามารถ" in result.assistant_message
    )
    assert "สำเร็จ" not in result.assistant_message


def test_confirmation_templates_exist():
    for code in (
        "AGGRESSIVE_CLEANING",
        "AMBIGUOUS_MAPPING",
        "BUSINESS_CONTRACT_CHANGE",
        "DESTRUCTIVE_TRANSFORM",
        "SEMANTIC_MEANING_REQUIRED",
    ):
        assert template_for_reason_code(code) is not None
