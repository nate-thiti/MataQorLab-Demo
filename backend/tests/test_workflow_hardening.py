"""Phase 4.5 — Pre-AI workflow hardening tests."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.tools.registry import STEP_REGISTRY, resolve_step_type
from app.services.workflow.capability import (
    WorkflowPersistenceError,
    allow_begin_step_fallback,
    ensure_workflow_persistence_ready,
    reset_workflow_capability_cache,
)
from app.services.workflow.engine import ConfirmationRequired, WorkflowEngine
from app.services.workflow.models import WorkflowErrorCode
from app.services.workflow.orchestrator_context import build_orchestrator_workflow_context
from app.services.workflow.policies import (
    build_step_fingerprint,
    evaluate_confirmation_requirement,
)
from app.services.workflow.state import begin_step


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
    def __init__(self, session=None, steps=None, *, rpc_error=True):
        self.rpc_error = rpc_error
        self.rpc_calls = []
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

    def rpc(self, name, params=None):
        self.rpc_calls.append((name, params))

        class _Rpc:
            def __init__(self, outer):
                self.outer = outer

            def execute(self_inner):
                if self.outer.rpc_error:
                    raise RuntimeError("rpc unavailable")
                return SimpleNamespace(data=[])

        return _Rpc(self)


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


def _engine(client):
    return WorkflowEngine(client=client, skip_capability_check=True)


def test_step_registry_is_canonical():
    assert set(STEP_REGISTRY) == {
        "inspect", "prepare", "map", "validate", "clean", "finalize"
    }
    assert resolve_step_type("clean_data") == "clean"


def test_aggressive_clean_requires_confirmation_and_does_not_run_handler(monkeypatch):
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
    }
    fp = lambda step: build_step_fingerprint(step, session=session, dataset_key="sales.xlsx")
    steps = [
        _step("inspect", "completed", input=fp("inspect")),
        _step("prepare", "completed", input=fp("prepare"),
              output={"artifacts": {"dataset_key": "sales.xlsx"}}),
        _step("map", "completed", input=fp("map")),
        _step("validate", "completed", input=fp("validate")),
    ]
    client = _FakeClient(session=session, steps=steps)
    engine = _engine(client)
    engine._context["dataset_key"] = "sales.xlsx"
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("clean handler must not run")

    monkeypatch.setattr(
        "app.services.workflow.runners.run_clean_step", boom
    )
    with pytest.raises(ConfirmationRequired) as exc:
        engine.execute_step("sess-1", "clean", user_id="user-1", session=session)
    assert called["n"] == 0
    assert exc.value.decision.action == "awaiting_user"
    assert exc.value.decision.reason == "AGGRESSIVE_CLEANING"
    clean_rows = [
        r for r in client.store["workflow_steps"] if r["step_type"] == "clean"
    ]
    assert any(r["status"] == "awaiting_user" for r in clean_rows)


def test_approved_confirmation_allows_execute(monkeypatch):
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
    }
    proposed = build_step_fingerprint(
        "clean", session=session, dataset_key="sales.xlsx"
    )
    conf = evaluate_confirmation_requirement(
        session, "clean", proposed_input=proposed
    )
    assert conf.required is True
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
    engine = _engine(client)
    engine._context["dataset_key"] = "sales.xlsx"
    engine.resolve_awaiting_user(
        "sess-1",
        "clean",
        user_id="user-1",
        resolution={"decision": "approved"},
    )
    ran = {"n": 0}

    def fake_clean(*_a, **_k):
        ran["n"] += 1
        from app.services.tools.types import ToolResult
        return ToolResult(
            tool="clean_data",
            status="completed",
            summary="ok",
            artifacts={"cleaned_artifact_key": "c.parquet", "dataset_key": "sales.xlsx"},
        )

    monkeypatch.setattr("app.services.workflow.runners.run_clean_step", fake_clean)
    result = engine.execute_step("sess-1", "clean", user_id="user-1", session=session)
    assert ran["n"] == 1
    assert result.status == "completed"


def test_rejected_confirmation_does_not_execute(monkeypatch):
    session = _FakeClient().store["data_setup_sessions"][0]
    session = {**session, "cleaning_profile": "aggressive"}
    conf = evaluate_confirmation_requirement(session, "clean")
    steps = [
        _step(
            "clean",
            "awaiting_user",
            input={
                **build_step_fingerprint("clean", session=session),
                "confirmation_fingerprint": conf.confirmation_fingerprint,
                "reason_code": "AGGRESSIVE_CLEANING",
            },
        )
    ]
    client = _FakeClient(session=session, steps=steps)
    engine = _engine(client)
    row = engine.resolve_awaiting_user(
        "sess-1",
        "clean",
        user_id="user-1",
        resolution={"decision": "rejected"},
        reason="user said no",
    )
    assert row["engine_action"] == "blocked"
    assert row["resolution"]["decision"] == "rejected"

    def boom(*_a, **_k):
        raise AssertionError("must not run")

    monkeypatch.setattr("app.services.workflow.runners.run_clean_step", boom)
    with pytest.raises(RuntimeError):
        engine.execute_step("sess-1", "clean", user_id="user-1", session=session)


def test_confirmation_fingerprint_change_invalidates_pending():
    session = {
        "id": "sess-1",
        "user_id": "user-1",
        "status": "processing",
        "source_type": "file",
        "source_fingerprint": "src-v1",
        "column_mapping": {"a": "sales"},
        "cleaning_profile": "aggressive",
        "cleaning_recipe": {},
        "source_ref": {"file_name": "sales.xlsx"},
    }
    conf = evaluate_confirmation_requirement(session, "clean")
    steps = [
        _step(
            "clean",
            "awaiting_user",
            input={
                **build_step_fingerprint("clean", session=session, dataset_key=""),
                "confirmation_fingerprint": conf.confirmation_fingerprint,
                "reason_code": "AGGRESSIVE_CLEANING",
            },
        )
    ]
    client = _FakeClient(session=session, steps=steps)
    engine = _engine(client)
    changed = {**session, "cleaning_profile": "standard"}
    engine.sync_input_validity("sess-1", changed)
    by_status = {r["step_type"]: r["status"] for r in client.store["workflow_steps"]}
    assert by_status["clean"] == "stale"


def test_missing_fingerprint_not_reusable():
    steps = [
        _step("inspect", "completed", input={}),  # legacy empty
    ]
    engine = _engine(_FakeClient(steps=steps))
    decision = engine.get_next_action("sess-1")
    assert decision.action == "execute"
    assert decision.step_type == "inspect"


def test_awaiting_user_blocks_run_until_idle(monkeypatch):
    steps = [
        _step("inspect", "completed", input={"source_fingerprint": "src-v1", "source_type": "file"}),
        _step("prepare", "awaiting_user", reason="SEMANTIC_MEANING_REQUIRED"),
    ]
    client = _FakeClient(steps=steps)
    engine = _engine(client)
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("no execute while awaiting")

    monkeypatch.setattr(engine, "execute_step", boom)
    decision = engine.run_until_idle("sess-1", user_id="user-1")
    assert decision.action == "awaiting_user"
    assert called["n"] == 0


def test_process_data_setup_session_uses_engine(monkeypatch):
    import app.services.data_setup as data_setup

    calls = {"run": 0}
    session_row = {
        "id": "s1",
        "user_id": "u1",
        "status": "approved",
    }

    class _Eng:
        def __init__(self, *a, **k):
            pass

        def get_next_action(self, *a, **k):
            from app.services.workflow.models import WorkflowDecision
            return WorkflowDecision(action="complete", reason="ready")

        def run_until_idle(self, *a, **k):
            calls["run"] += 1
            session_row["status"] = "ready"
            from app.services.workflow.models import WorkflowDecision
            return WorkflowDecision(
                action="complete",
                step_type="finalize",
                reason="done",
            )

    class _Client:
        def table(self, name):
            q = MagicMock()
            q.select.return_value = q
            q.eq.return_value = q
            q.limit.return_value = q
            q.update.return_value = q

            def _exec():
                if name == "data_setup_sessions":
                    return SimpleNamespace(data=[dict(session_row)])
                return SimpleNamespace(data=[])

            q.execute.side_effect = _exec
            return q

    monkeypatch.setattr(data_setup, "get_supabase_client", lambda: _Client())
    monkeypatch.setattr(
        "app.services.workflow.engine.WorkflowEngine",
        _Eng,
    )
    monkeypatch.setattr(
        "app.services.workflow.state.update_session_summary",
        lambda *a, **k: None,
    )
    data_setup.process_data_setup_session("s1", "u1")
    assert calls["run"] == 1


def test_production_rpc_unavailable_fails_closed(monkeypatch):
    reset_workflow_capability_cache()
    monkeypatch.setattr(
        "app.services.workflow.capability.settings.APP_ENV",
        "production",
    )
    monkeypatch.setattr(
        "app.services.workflow.capability.settings.WORKFLOW_ALLOW_BEGIN_STEP_FALLBACK",
        None,
    )
    assert allow_begin_step_fallback() is False
    client = _FakeClient(rpc_error=True)
    with pytest.raises(WorkflowPersistenceError, match="WORKFLOW_RPC_UNAVAILABLE"):
        begin_step("sess-1", "inspect", client=client)


def test_dev_fallback_allowed(monkeypatch):
    reset_workflow_capability_cache()
    monkeypatch.setattr(
        "app.services.workflow.capability.settings.APP_ENV",
        "development",
    )
    monkeypatch.setattr(
        "app.services.workflow.capability.settings.WORKFLOW_ALLOW_BEGIN_STEP_FALLBACK",
        None,
    )
    assert allow_begin_step_fallback() is True
    client = _FakeClient(rpc_error=True)
    row = begin_step("sess-1", "inspect", client=client, input_payload={"source_fingerprint": "x"})
    assert row["status"] == "running"
    mode = ensure_workflow_persistence_ready(client, force=True)
    assert mode == "fallback"


def test_orchestrator_context_excludes_sensitive_fields():
    from app.services.workflow.models import WorkflowDecision, WorkflowPlan, WorkflowPlanStep

    plan = WorkflowPlan(
        session_id="sess-1",
        status="awaiting_user",
        current_step="clean",
        next_action=WorkflowDecision(
            action="awaiting_user",
            step_type="clean",
            reason="AGGRESSIVE_CLEANING",
            metadata={
                "profile": "aggressive",
                "password": "should-strip",
                "token": "nope",
                "service_role": "secret",
                "signed_url": "https://x",
                "traceback": "Traceback...",
                "raw_dataframe": "<df>",
            },
        ),
        steps=[
            WorkflowPlanStep(step_type="inspect", status="completed"),
            WorkflowPlanStep(step_type="clean", status="awaiting_user"),
        ],
        awaiting_user={
            "step_type": "clean",
            "reason": "AGGRESSIVE_CLEANING",
            "secret": "no",
        },
    )
    ctx = build_orchestrator_workflow_context(plan)
    blob = json.dumps(ctx).lower()
    for banned in (
        "password", "token", "secret", "service_role",
        "signed_url", "traceback", "raw_dataframe",
    ):
        assert banned not in blob or banned == "secret" and "\"secret\"" not in blob
    assert "password" not in blob
    assert "signed_url" not in blob
    assert "traceback" not in blob
    assert ctx["steps"]["clean"] == "awaiting_user"
    assert ctx["next_action"]["reason"] == "AGGRESSIVE_CLEANING"
    assert len(json.dumps(ctx)) < 8000


def test_standard_clean_no_confirmation():
    decision = evaluate_confirmation_requirement(
        {"cleaning_profile": "standard", "source_fingerprint": "x"},
        "clean",
    )
    assert decision.required is False


def test_ambiguous_mapping_flag_requires_confirmation():
    decision = evaluate_confirmation_requirement(
        {
            "require_mapping_confirmation": True,
            "column_mapping": {"a": "sales"},
            "source_fingerprint": "x",
        },
        "map",
    )
    assert decision.required is True
    assert decision.reason_code == "AMBIGUOUS_MAPPING"
