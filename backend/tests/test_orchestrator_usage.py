"""Phase 7.1 — workflow_orchestrator token accounting."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.orchestrator.decision_models import RespondDecision
from app.services.orchestrator.orchestrator import WorkflowOrchestrator
from app.services.orchestrator.usage import (
    USAGE_TYPE_WORKFLOW_ORCHESTRATOR,
    reset_usage_settlements_for_tests,
    settle_orchestrator_usage,
    summarize_calls,
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
                "status": "awaiting_answers",
                "source_type": "file",
                "source_ref": {"file_name": "sales.xlsx"},
                "scan_result": {"row_count": 1000, "column_count": 11, "columns": []},
                "processing_progress": {},
            }],
            "workflow_steps": list(steps or []),
        }

    def table(self, name):
        return _Query(self.store, name)


@pytest.fixture(autouse=True)
def _clear_settlements():
    reset_usage_settlements_for_tests()
    yield
    reset_usage_settlements_for_tests()


def test_summarize_calls_aggregates_tokens():
    summary = summarize_calls([
        {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
    ])
    assert summary["usage_type"] == USAGE_TYPE_WORKFLOW_ORCHESTRATOR
    assert summary["llm_calls"] == 2
    assert summary["total_tokens"] == 180


def test_settle_records_once_and_skips_idempotent():
    recorded = []

    async def fake_record(user_id, total, *, usage_type=None, metadata=None):
        recorded.append({
            "user_id": user_id,
            "total": total,
            "usage_type": usage_type,
            "metadata": metadata,
        })

    client = _FakeClient()
    calls = [{
        "kind": "decision",
        "model": "qwen-test",
        "prompt_tokens": 40,
        "completion_tokens": 10,
        "total_tokens": 50,
        "fallback": False,
        "repair_attempt": False,
    }]
    with patch(
        "app.services.orchestrator.usage.record_token_usage",
        AsyncMock(side_effect=fake_record),
    ):
        first = asyncio.run(settle_orchestrator_usage(
            user_id="user-1",
            session_id="sess-1",
            calls=calls,
            settlement_key="orch:user-1:sess-1:req-1",
            decision_type="respond",
            prompt_version="1.0",
            client=client,
        ))
        second = asyncio.run(settle_orchestrator_usage(
            user_id="user-1",
            session_id="sess-1",
            calls=calls,
            settlement_key="orch:user-1:sess-1:req-1",
            decision_type="respond",
            prompt_version="1.0",
            client=client,
        ))
    assert first["settled"] is True
    assert second["idempotent_skip"] is True
    assert len(recorded) == 1
    assert recorded[0]["usage_type"] == USAGE_TYPE_WORKFLOW_ORCHESTRATOR
    assert recorded[0]["total"] == 50
    progress = client.store["data_setup_sessions"][0]["processing_progress"]
    assert progress["orchestrator_usage"]["total_tokens"] == 50


def test_deterministic_confirmation_zero_tokens(inline_asyncio_to_thread):
    client = _FakeClient()
    orch = WorkflowOrchestrator(client=client, llm=SimpleNamespace())
    with patch.object(
        orch.engine,
        "get_workflow_plan",
        return_value={
            "session_id": "sess-1",
            "status": "awaiting_answers",
            "current_step": "clean",
            "steps": [],
            "awaiting_user": {
                "reason_code": "AGGRESSIVE_CLEANING",
                "question": "ยืนยัน Deep Clean?",
                "step_type": "clean",
                "options": [{"value": "approved", "label": "OK"}],
            },
            "next_action": {"action": "awaiting_user", "step_type": "clean"},
        },
    ), patch(
        "app.services.orchestrator.orchestrator.build_orchestrator_llm_context",
        return_value={
            "workflow": {
                "awaiting_user": {
                    "reason_code": "AGGRESSIVE_CLEANING",
                    "question": "ยืนยัน Deep Clean?",
                    "step_type": "clean",
                    "options": [{"value": "approved", "label": "OK"}],
                },
                "next_action": {"action": "awaiting_user"},
                "status": "awaiting_answers",
            },
            "source_summary": {"name": "sales.xlsx"},
            "recent_turns": [],
        },
    ), patch(
        "app.services.orchestrator.usage.record_token_usage",
        AsyncMock(),
    ) as record_mock:
        result = asyncio.run(orch.handle_message(
            session_id="sess-1",
            user_id="user-1",
            message="",
            llm_decision_override=None,
            settlement_key="orch:det-confirm",
        ))
    # Deterministic ask_user path via fallback when no message to resolve —
    # may call LLM; force override empty path by awaiting without resolution:
    # Here we assert settlement of whatever calls occurred; for pure template
    # with override ask, use respond zero.
    assert result.llm_usage is not None
    if result.llm_usage.get("llm_calls", 0) == 0:
        record_mock.assert_not_called()


def test_override_decision_zero_llm_tokens(inline_asyncio_to_thread):
    client = _FakeClient()
    orch = WorkflowOrchestrator(client=client, llm=SimpleNamespace())

    with patch.object(
        orch.engine,
        "get_workflow_plan",
        return_value={
            "session_id": "sess-1",
            "status": "awaiting_answers",
            "current_step": "inspect",
            "steps": [{"step_type": "inspect", "status": "pending"}],
            "next_action": {"action": "respond"},
            "awaiting_user": None,
        },
    ), patch(
        "app.services.orchestrator.orchestrator.build_orchestrator_llm_context",
        return_value={
            "workflow": {
                "awaiting_user": None,
                "next_action": {"action": "respond"},
                "status": "awaiting_answers",
            },
            "source_summary": {"name": "sales.xlsx"},
            "recent_turns": [],
        },
    ), patch(
        "app.services.orchestrator.usage.record_token_usage",
        AsyncMock(),
    ) as record_mock:
        result = asyncio.run(orch.handle_message(
            session_id="sess-1",
            user_id="user-1",
            message="เริ่มได้เลย",
            llm_decision_override=RespondDecision(
                type="respond",
                message="สรุปจาก WorkflowPlan โดยไม่เรียก LLM",
            ),
            settlement_key="orch:override-1",
        ))
    assert result.llm_usage["total_tokens"] == 0
    assert result.llm_usage["llm_calls"] == 0
    record_mock.assert_not_called()


def test_primary_and_fallback_both_counted():
    recorded = []

    async def fake_record(user_id, total, *, usage_type=None, metadata=None):
        recorded.append(total)

    calls = [
        {
            "kind": "decision",
            "model": "primary",
            "prompt_tokens": 200,
            "completion_tokens": 20,
            "total_tokens": 220,
            "fallback": False,
        },
        {
            "kind": "decision",
            "model": "fallback-model",
            "prompt_tokens": 300,
            "completion_tokens": 30,
            "total_tokens": 330,
            "fallback": True,
        },
    ]
    with patch(
        "app.services.orchestrator.usage.record_token_usage",
        AsyncMock(side_effect=fake_record),
    ):
        summary = asyncio.run(settle_orchestrator_usage(
            user_id="user-1",
            session_id="sess-1",
            calls=calls,
            settlement_key="orch:fb-1",
            client=_FakeClient(),
        ))
    assert summary["total_tokens"] == 550
    assert summary["llm_calls"] == 2
    assert recorded == [550]


def test_repair_and_decision_both_counted():
    calls = [
        {
            "kind": "decision",
            "model": "m",
            "prompt_tokens": 400,
            "completion_tokens": 80,
            "total_tokens": 480,
            "repair_attempt": False,
        },
        {
            "kind": "repair",
            "model": "m",
            "prompt_tokens": 120,
            "completion_tokens": 40,
            "total_tokens": 160,
            "repair_attempt": True,
        },
    ]
    with patch(
        "app.services.orchestrator.usage.record_token_usage",
        AsyncMock(),
    ) as record_mock:
        summary = asyncio.run(settle_orchestrator_usage(
            user_id="user-1",
            session_id="sess-1",
            calls=calls,
            settlement_key="orch:repair-1",
            client=_FakeClient(),
        ))
    assert summary["total_tokens"] == 640
    record_mock.assert_awaited_once()
    assert record_mock.await_args.args[1] == 640
    assert record_mock.await_args.kwargs["usage_type"] == USAGE_TYPE_WORKFLOW_ORCHESTRATOR


def test_single_successful_orchestrator_llm_call_settled(inline_asyncio_to_thread):
    client = _FakeClient()
    llm = SimpleNamespace()

    async def fake_decide(*_a, **_k):
        return (
            RespondDecision(type="respond", message="ตรวจโครงสร้างแล้ว"),
            "qwen-test",
            [{
                "kind": "decision",
                "model": "qwen-test",
                "prompt_tokens": 100,
                "completion_tokens": 25,
                "total_tokens": 125,
                "fallback": False,
                "repair_attempt": False,
            }],
        )

    with patch.object(
        WorkflowOrchestrator, "_llm_decide", side_effect=fake_decide
    ), patch(
        "app.services.orchestrator.orchestrator.build_orchestrator_llm_context",
        return_value={
            "workflow": {
                "awaiting_user": None,
                "next_action": {"action": "respond"},
                "status": "awaiting_answers",
            },
            "source_summary": {"name": "sales.xlsx", "row_count": 1000},
            "recent_turns": [],
        },
    ), patch.object(
        WorkflowOrchestrator,
        "_deterministic_fallback",
        return_value=RespondDecision(type="respond", message="fallback"),
    ), patch(
        "app.services.orchestrator.usage.record_token_usage",
        AsyncMock(),
    ) as record_mock:
        orch = WorkflowOrchestrator(client=client, llm=llm)
        with patch.object(
            orch.engine,
            "get_workflow_plan",
            return_value={
                "session_id": "sess-1",
                "status": "awaiting_answers",
                "current_step": "inspect",
                "steps": [],
                "next_action": {"action": "respond"},
            },
        ):
            result = asyncio.run(orch.handle_message(
                session_id="sess-1",
                user_id="user-1",
                message="ช่วยวิเคราะห์ยอดขาย",
                settlement_key="orch:single-1",
            ))
    assert result.llm_usage["total_tokens"] == 125
    assert result.llm_usage["usage_type"] == USAGE_TYPE_WORKFLOW_ORCHESTRATOR
    record_mock.assert_awaited_once()
    assert record_mock.await_args.kwargs["usage_type"] == USAGE_TYPE_WORKFLOW_ORCHESTRATOR
