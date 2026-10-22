"""Shared fakes/helpers for Phase 7 E2E scenario tests."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

from app.services.tools.types import ToolResult
from app.services.workflow.engine import WorkflowEngine
from app.services.workflow.policies import build_step_fingerprint

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "workflow"


class _Query:
    def __init__(self, store, table, payload=None, filters=None):
        self.store = store
        self.table_name = table
        self.payload = payload or {}
        self.filters = dict(filters or {})
        self._in_filters: Dict[str, List[Any]] = {}
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

    def in_(self, key, values):
        self._in_filters[key] = list(values)
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
            and all(row.get(k) in vals for k, vals in self._in_filters.items())
        ]
        for key, desc in reversed(self._order):
            def _sort_key(row, k=key):
                value = row.get(k)
                if value is None:
                    return (1, "")
                # Avoid TypeError when mixing missing ints with ISO timestamps.
                if isinstance(value, (int, float)):
                    return (0, value)
                return (0, str(value))

            matched.sort(key=_sort_key, reverse=desc)
        if self._limit is not None:
            matched = matched[: self._limit]
        return SimpleNamespace(data=[dict(r) for r in matched])


class FakeClient:
    def __init__(self, session=None, steps=None):
        self.store = {
            "data_setup_sessions": [session or default_session()],
            "workflow_steps": list(steps or []),
        }
        self.begin_calls = 0

    def table(self, name):
        return _Query(self.store, name)

    def rpc(self, *_a, **_k):
        class _Rpc:
            def execute(self_inner):
                raise RuntimeError("rpc unavailable")

        return _Rpc()


def default_session(**overrides) -> Dict[str, Any]:
    base = {
        "id": "sess-e2e-1",
        "user_id": "user-e2e-1",
        "status": "processing",
        "source_type": "file",
        "source_fingerprint": "src-e2e-v1",
        "column_mapping": {
            "invoice_date": "date",
            "amount": "sales",
            "customer_code": "customer",
        },
        "cleaning_profile": "standard",
        "cleaning_recipe": {
            "data_contract": {
                "row_grain": "invoice_line",
                "mapping_confirmed": True,
                "business_context_reviewed": True,
                "negative_sales_are_returns": True,
            }
        },
        "source_ref": {"file_name": "sales_clean.csv"},
        "scan_result": {
            "row_count": 5,
            "column_count": 7,
            "columns": [
                {"name": "invoice_date"},
                {"name": "amount"},
                {"name": "customer_code"},
            ],
        },
        "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:10:00+00:00",
    }
    base.update(overrides)
    return base


def step_row(step_type: str, status: str, **extra) -> Dict[str, Any]:
    session_id = extra.pop("session_id", "sess-e2e-1")
    version = extra.pop("version", 1)
    attempt = extra.pop("attempt", 1)
    artifacts = extra.pop("artifacts", None)
    output = extra.pop("output", None)
    if output is None:
        output = {
            "tool": step_type,
            "status": "completed" if status == "completed" else status,
            "summary": f"{step_type} {status}",
            "artifacts": artifacts or {},
        }
    row = {
        "id": f"{step_type}-{status}-v{version}-a{attempt}",
        "data_setup_session_id": session_id,
        "step_type": step_type,
        "status": status,
        "version": version,
        "attempt": attempt,
        "input": extra.pop("input", {"fingerprint": "fp"}),
        "output": output,
        "retryable": extra.pop("retryable", status == "failed"),
        "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:05:00+00:00",
        **extra,
    }
    return row


def completed_chain(
    *,
    through: str = "clean",
    session: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    order = ["inspect", "prepare", "map", "validate", "clean", "finalize"]
    session = session or default_session()
    rows = []
    for step_type in order:
        fp = build_step_fingerprint(
            step_type,
            session=session,
            dataset_key="ds-e2e",
            cleaning_profile=session.get("cleaning_profile"),
        )
        artifacts = {"dataset_key": "ds-e2e"}
        if step_type == "clean":
            artifacts["cleaned_artifact_key"] = "cleaned/sess-e2e-1/v1.parquet"
        if step_type == "finalize":
            artifacts["dataset_version_id"] = "dv-e2e-1"
        rows.append(step_row(
            step_type,
            "completed",
            input=fp,
            artifacts=artifacts,
        ))
        if step_type == through:
            break
    return rows


def make_engine(client: FakeClient) -> WorkflowEngine:
    return WorkflowEngine(client=client)


def install_success_runners(
    monkeypatch,
    *,
    fail_steps: Optional[Dict[str, int]] = None,
):
    """Mock engine._dispatch_runner with deterministic ToolResults.

    ``fail_steps`` maps step_type → remaining failures before success.
    """
    remaining = dict(fail_steps or {})

    def fake_dispatch(self, step, user_id, session_id, session):
        left = int(remaining.get(step, 0))
        if left > 0:
            remaining[step] = left - 1
            return ToolResult(
                tool=step,
                status="failed",
                summary=f"forced failure for {step}",
            )
        artifacts = {"dataset_key": "ds-e2e"}
        if step == "clean":
            artifacts["cleaned_artifact_key"] = f"cleaned/{session_id}/v1.parquet"
        if step == "finalize":
            artifacts["dataset_version_id"] = "dv-e2e-1"
            # Mirror finalize side-effect: mark session ready.
            self.client.table("data_setup_sessions").update({
                "status": "ready",
                "output_file": "sales_ready.parquet",
                "dataset_version_id": "dv-e2e-1",
                "updated_at": "2026-08-01T01:00:00+00:00",
            }).eq("id", session_id).eq("user_id", user_id).execute()
        return ToolResult(
            tool=step,
            status="completed",
            summary=f"{step} completed",
            artifacts=artifacts,
            findings=[],
            warnings=[],
        )

    monkeypatch.setattr(WorkflowEngine, "_dispatch_runner", fake_dispatch)
    return remaining


def history_summary(client: FakeClient, session_id: str = "sess-e2e-1") -> List[str]:
    rows = [
        r for r in client.store["workflow_steps"]
        if r.get("data_setup_session_id") == session_id
    ]
    rows.sort(key=lambda r: (r.get("step_type") or "", r.get("version") or 0, r.get("attempt") or 0))
    return [
        f"{r['step_type']} v{r.get('version')} attempt{r.get('attempt')} {r.get('status')}"
        for r in rows
    ]


def fixture_path(name: str) -> Path:
    return FIXTURES / name
