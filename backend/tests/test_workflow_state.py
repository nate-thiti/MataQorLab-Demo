"""Phase 3 — workflow step persistence and resume helpers."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.tools.types import ToolResult
from app.services.workflow.models import (
    SETUP_SEQUENCE,
    WorkflowStepStatus,
    WorkflowStepType,
)
from app.services.workflow.state import (
    execute_persisted_tool_step,
    get_resume_state,
    is_reusable,
    tool_result_to_output,
)


class _Query:
    def __init__(self, store, table, payload=None, filters=None):
        self.store = store
        self.table_name = table
        self.payload = payload or {}
        self.filters = filters or {}
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
            row = {
                "id": f"{self.table_name}-{len(rows)+1}",
                **self.payload,
            }
            rows.append(row)
            return SimpleNamespace(data=[row])
        if self._op == "update":
            updated = []
            for row in rows:
                if all(row.get(k) == v for k, v in self.filters.items()):
                    row.update(self.payload)
                    updated.append(row)
            return SimpleNamespace(data=updated)
        matched = [
            row for row in rows
            if all(row.get(k) == v for k, v in self.filters.items())
        ]
        for key, desc in reversed(self._order):
            matched.sort(key=lambda r: r.get(key) or 0, reverse=desc)
        if self._limit is not None:
            matched = matched[: self._limit]
        return SimpleNamespace(data=matched)


class _FakeClient:
    def __init__(self):
        self.store = {
            "workflow_steps": [],
            "data_setup_sessions": [
                {"id": "sess-1", "user_id": "user-1", "status": "processing"}
            ],
        }
        self.rpc_calls = []

    def table(self, name):
        return _Query(self.store, name)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))

        class _Rpc:
            def __init__(self, outer, params):
                self.outer = outer
                self.params = params

            def execute(self):
                # Simulate RPC unavailable → fallback path in begin_step.
                raise RuntimeError("rpc unavailable")

        return _Rpc(self, params)


def test_tool_result_to_output_is_compact():
    result = ToolResult(
        tool="clean_data",
        status="completed",
        summary="Cleaning completed",
        findings=[{"type": "duplicate_rows_removed", "count": 2}],
        artifacts={"cleaned_artifact_key": "data_setup_x_cleaned_v1.parquet"},
        metadata={"rows_after": 10},
    )
    output = tool_result_to_output(result)
    assert output["tool"] == "clean_data"
    assert output["artifacts"]["cleaned_artifact_key"].endswith(".parquet")
    assert "DataFrame" not in str(output)


def test_status_model_covers_phase3_values():
    assert WorkflowStepStatus.COMPLETED.value == "completed"
    assert WorkflowStepStatus.FAILED.value == "failed"
    assert WorkflowStepStatus.STALE.value == "stale"
    assert [s.value for s in SETUP_SEQUENCE] == [
        "inspect", "prepare", "map", "validate", "clean", "finalize"
    ]


def test_execute_persisted_tool_step_records_completed_and_reuses(monkeypatch):
    client = _FakeClient()
    calls = {"n": 0}

    def runner():
        calls["n"] += 1
        return ToolResult(
            tool="prepare_data",
            status="completed",
            summary="prepared",
            artifacts={"dataset_key": "sales.xlsx"},
        )

    step1, result1, reused1, _ = execute_persisted_tool_step(
        session_id="sess-1",
        user_id="user-1",
        step_type=WorkflowStepType.PREPARE,
        input_payload={"source_type": "file"},
        runner=runner,
        client=client,
    )
    assert reused1 is False
    assert result1 is not None
    assert result1.artifacts["dataset_key"] == "sales.xlsx"
    assert step1["status"] == "completed"
    assert calls["n"] == 1

    step2, result2, reused2, _ = execute_persisted_tool_step(
        session_id="sess-1",
        user_id="user-1",
        step_type=WorkflowStepType.PREPARE,
        input_payload={"source_type": "file"},
        runner=runner,
        client=client,
    )
    assert reused2 is True
    assert calls["n"] == 1
    assert is_reusable(step2)
    assert result2 is not None
    assert result2.artifacts["dataset_key"] == "sales.xlsx"


def test_execute_persisted_tool_step_records_failure(monkeypatch):
    client = _FakeClient()

    def runner():
        raise RuntimeError("boom cleaning")

    with pytest.raises(RuntimeError, match="boom cleaning"):
        execute_persisted_tool_step(
            session_id="sess-1",
            user_id="user-1",
            step_type=WorkflowStepType.CLEAN,
            runner=runner,
            client=client,
        )
    rows = client.store["workflow_steps"]
    assert rows[-1]["status"] == "failed"
    assert rows[-1]["error_code"] == "CLEANING_EXECUTION_FAILED"
    assert "boom" in (rows[-1].get("error_message") or "")


def test_get_resume_state_points_at_failed_step():
    client = _FakeClient()
    client.store["workflow_steps"] = [
        {
            "data_setup_session_id": "sess-1",
            "step_type": "inspect",
            "status": "completed",
            "version": 1,
            "attempt": 1,
            "output": {"tool": "inspect_source", "status": "completed"},
        },
        {
            "data_setup_session_id": "sess-1",
            "step_type": "prepare",
            "status": "completed",
            "version": 1,
            "attempt": 1,
            "output": {
                "tool": "prepare_data",
                "status": "completed",
                "artifacts": {"dataset_key": "sales.xlsx"},
            },
        },
        {
            "data_setup_session_id": "sess-1",
            "step_type": "map",
            "status": "failed",
            "version": 1,
            "attempt": 1,
            "error_code": "MAP_EXECUTION_FAILED",
            "output": {},
        },
    ]
    resume = get_resume_state("sess-1", client=client)
    assert resume["last_failed_step"] == "map"
    assert resume["next_step"] == "map"
    assert resume["steps"]["prepare"]["status"] == "completed"


def test_finalize_idempotent_when_already_ready():
    from app.services.tools.finalize import finalize_data_setup

    class Client:
        def table(self, name):
            self.name = name
            return self

        def select(self, *_a, **_k):
            return self

        def eq(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def execute(self):
            return SimpleNamespace(data=[{
                "id": "sess-1",
                "status": "ready",
                "output_file": "etl_dataset_abc.parquet",
                "dataset_version_id": "dv-1",
                "recipe_id": "r-1",
                "run_id": "run-1",
                "output_dataset_key": "etl:recipe:r-1",
                "recipe_hash": "h1",
                "contract_hash": "h2",
            }])

    result = finalize_data_setup(
        user_id="user-1",
        session={"id": "sess-1"},
        dataset_key="sales.xlsx",
        recipe={
            "column_mapping": {
                "order_id": "order_id",
                "net_amount": "net_amount",
            },
            "data_contract": {
                "mapping_confirmed": True,
                "business_context_reviewed": True,
            },
        },
        client=Client(),
    )
    assert result.status == "completed"
    assert result.artifacts.get("reused") is True
    assert result.artifacts["output_file"] == "etl_dataset_abc.parquet"
