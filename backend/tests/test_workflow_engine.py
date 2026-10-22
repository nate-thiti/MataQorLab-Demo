"""Phase 4 — Workflow Engine dependency, transition, stale, skip, awaiting_user."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.tools.registry import UnknownStepError, resolve_step_type
from app.services.workflow.dependencies import STEP_DEPENDENCIES, invalidation_targets
from app.services.workflow.engine import WorkflowEngine
from app.services.workflow.models import (
    WorkflowErrorCode,
    WorkflowStepStatus,
    WorkflowStepType,
)
from app.services.workflow.policies import build_step_fingerprint, can_skip
from app.services.workflow.transitions import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    assert_transition,
    can_transition,
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
                "scan_result": {"columns": [{"name": "a"}]},
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


def test_transition_matrix_rejects_completed_to_running():
    assert can_transition("completed", "stale")
    assert can_transition("running", "completed")
    assert not can_transition("completed", "running")
    with pytest.raises(InvalidTransitionError):
        assert_transition("completed", "running")
    assert "stale" in ALLOWED_TRANSITIONS["completed"]
    assert "superseded" in ALLOWED_TRANSITIONS["completed"]


def test_dependency_graph_matches_phase4_contract():
    assert STEP_DEPENDENCIES["prepare"] == {"inspect"}
    assert STEP_DEPENDENCIES["clean"] == {"prepare"}
    assert STEP_DEPENDENCIES["map"] == {"inspect"}
    assert STEP_DEPENDENCIES["validate"] == {"prepare", "map"}
    assert STEP_DEPENDENCIES["finalize"] == {"clean", "validate"}
    assert "validate" in invalidation_targets("map")
    assert "finalize" in invalidation_targets("map")
    assert "clean" not in invalidation_targets("map")


def test_unknown_step_fails_closed():
    with pytest.raises(UnknownStepError):
        resolve_step_type("drop_table")


def test_prepare_blocked_before_inspect():
    engine = WorkflowEngine(client=_FakeClient(steps=[]), skip_capability_check=True)
    decision = engine.can_execute_step("sess-1", "prepare")
    assert decision.action == "blocked"
    assert decision.error_code == WorkflowErrorCode.DEPENDENCY_NOT_SATISFIED.value
    assert "inspect" in decision.metadata["missing"]


def test_clean_blocked_before_prepare():
    steps = [
        _step("inspect", "completed"),
    ]
    engine = WorkflowEngine(client=_FakeClient(steps=steps), skip_capability_check=True)
    decision = engine.can_execute_step("sess-1", "clean")
    assert decision.action == "blocked"
    assert "prepare" in decision.metadata["missing"]


def test_finalize_blocked_when_clean_incomplete():
    steps = [
        _step("inspect", "completed"),
        _step("prepare", "completed", output={"artifacts": {"dataset_key": "sales.xlsx"}}),
        _step("map", "completed"),
        _step("validate", "completed"),
    ]
    engine = WorkflowEngine(client=_FakeClient(steps=steps), skip_capability_check=True)
    decision = engine.can_execute_step("sess-1", "finalize")
    assert decision.action == "blocked"
    assert "clean" in decision.metadata["missing"]


def test_finalize_blocked_when_validate_stale():
    steps = [
        _step("inspect", "completed"),
        _step("prepare", "completed"),
        _step("map", "completed"),
        _step("validate", "stale"),
        _step(
            "clean",
            "completed",
            output={"artifacts": {"cleaned_artifact_key": "x.parquet", "dataset_key": "sales.xlsx"}},
        ),
    ]
    engine = WorkflowEngine(client=_FakeClient(steps=steps), skip_capability_check=True)
    decision = engine.can_execute_step("sess-1", "finalize")
    assert decision.action == "blocked"
    assert "validate" in decision.metadata["missing"]


def test_get_next_action_retries_failed_clean_without_upstream():
    steps = [
        _step("inspect", "completed", input={"source_fingerprint": "src-v1", "source_type": "file"}),
        _step(
            "prepare",
            "completed",
            input={"source_fingerprint": "src-v1", "source_type": "file"},
            output={"artifacts": {"dataset_key": "sales.xlsx"}},
        ),
        _step("map", "completed", input={"source_fingerprint": "src-v1", "mapping_fp": build_step_fingerprint("map", session={"source_fingerprint": "src-v1", "source_type": "file", "column_mapping": {"a": "sales"}})["mapping_fp"]}),
        _step("validate", "completed", input=build_step_fingerprint("validate", session={
            "source_fingerprint": "src-v1",
            "source_type": "file",
            "column_mapping": {"a": "sales"},
            "cleaning_recipe": {"data_contract": {"row_grain": "order"}},
        })),
        _step("clean", "failed", error_code="CLEANING_EXECUTION_FAILED"),
    ]
    # Fix map fingerprint to match session
    session = _FakeClient().store["data_setup_sessions"][0]
    steps[2]["input"] = build_step_fingerprint("map", session=session)
    steps[3]["input"] = build_step_fingerprint("validate", session=session)
    engine = WorkflowEngine(client=_FakeClient(steps=steps), skip_capability_check=True)
    decision = engine.get_next_action("sess-1")
    assert decision.action == "retry"
    assert decision.step_type == "clean"


def test_mapping_change_invalidates_validate_and_finalize_not_clean():
    session = {
        "id": "sess-1",
        "user_id": "user-1",
        "status": "processing",
        "source_type": "file",
        "source_fingerprint": "src-v1",
        "column_mapping": {"a": "sales", "b": "qty"},  # changed
        "cleaning_profile": "standard",
        "cleaning_recipe": {"data_contract": {"row_grain": "order"}},
        "source_ref": {"file_name": "sales.xlsx"},
    }
    old_session = {**session, "column_mapping": {"a": "sales"}}
    steps = [
        _step("inspect", "completed", input=build_step_fingerprint("inspect", session=old_session)),
        _step("prepare", "completed", input=build_step_fingerprint("prepare", session=old_session),
              output={"artifacts": {"dataset_key": "sales.xlsx"}}),
        _step("map", "completed", input=build_step_fingerprint("map", session=old_session)),
        _step("validate", "completed", input=build_step_fingerprint("validate", session=old_session)),
        _step(
            "clean",
            "completed",
            input=build_step_fingerprint("clean", session=old_session, dataset_key="sales.xlsx"),
            output={"artifacts": {"cleaned_artifact_key": "c.parquet", "dataset_key": "sales.xlsx"}},
        ),
        _step("finalize", "completed", input=build_step_fingerprint("finalize", session=old_session, dataset_key="sales.xlsx")),
    ]
    client = _FakeClient(session=session, steps=steps)
    engine = WorkflowEngine(client=client, skip_capability_check=True)
    engine._context["dataset_key"] = "sales.xlsx"
    engine.sync_input_validity("sess-1", session)
    by_status = {
        row["step_type"]: row["status"]
        for row in client.store["workflow_steps"]
    }
    assert by_status["validate"] == "stale"
    assert by_status["finalize"] == "stale"
    assert by_status["clean"] == "completed"
    assert by_status["map"] == "stale"  # mapping fingerprint changed


def test_skip_policy():
    assert can_skip("clean") is True
    assert can_skip("prepare") is False
    assert can_skip("finalize") is False
    engine = WorkflowEngine(
        client=_FakeClient(steps=[
            _step("inspect", "completed"),
            _step("prepare", "completed"),
        ]),
        skip_capability_check=True,
    )
    with pytest.raises(RuntimeError, match="SKIP_NOT_ALLOWED"):
        engine.skip_step("sess-1", "prepare", user_id="user-1", reason="nope")


def test_awaiting_user_blocks_downstream():
    steps = [
        _step("inspect", "completed"),
        _step("prepare", "completed"),
        _step("map", "awaiting_user", reason="ambiguous_mapping"),
    ]
    engine = WorkflowEngine(client=_FakeClient(steps=steps), skip_capability_check=True)
    decision = engine.get_next_action("sess-1")
    assert decision.action == "awaiting_user"
    assert decision.step_type == "map"
    assert decision.error_code == WorkflowErrorCode.STEP_AWAITING_USER.value
    # Downstream should not be selected.
    assert decision.step_type != "validate"


def test_resolve_awaiting_user_returns_ready():
    steps = [
        _step(
            "map",
            "awaiting_user",
            reason="need confirm",
            input={
                "source_fingerprint": "src-v1",
                "source_type": "file",
                "mapping_fp": "x",
                "confirmation_fingerprint": "bound",
                "reason_code": "need confirm",
            },
        ),
    ]
    client = _FakeClient(steps=steps)
    engine = WorkflowEngine(client=client, skip_capability_check=True)
    # Fingerprint must still match current session or resolution fails closed.
    session = client.store["data_setup_sessions"][0]
    fp = build_step_fingerprint("map", session=session)
    conf_fp = __import__(
        "app.services.workflow.policies", fromlist=["build_confirmation_fingerprint"]
    ).build_confirmation_fingerprint(
        "map", session=session, proposed_input=fp, reason_code="need confirm"
    )
    steps[0]["input"]["confirmation_fingerprint"] = conf_fp
    steps[0]["input"].update(fp)
    row = engine.resolve_awaiting_user(
        "sess-1",
        "map",
        user_id="user-1",
        resolution={"decision": "approved"},
    )
    assert row["status"] == WorkflowStepStatus.READY.value


def test_workflow_plan_shape():
    steps = [
        _step("inspect", "completed"),
        _step("prepare", "completed"),
        _step("map", "failed"),
    ]
    engine = WorkflowEngine(client=_FakeClient(steps=steps), skip_capability_check=True)
    plan = engine.get_workflow_plan("sess-1")
    assert "steps" in plan
    assert plan["next_action"]["action"] in {"execute", "retry", "blocked"}
    assert any(item["step"] == "map" and item["retryable"] for item in plan["steps"])
