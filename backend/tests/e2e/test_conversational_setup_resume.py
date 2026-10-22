"""E2E-06 / E2E-07 / E2E-11 artifact — resume, duplicate dispatch, missing artifact."""
from __future__ import annotations

from app.services.tools.types import ToolResult

from .helpers import (
    FakeClient,
    completed_chain,
    default_session,
    history_summary,
    install_success_runners,
    make_engine,
)


def test_e2e06_restart_resume_reuses_upstream_runs_finalize(monkeypatch):
    monkeypatch.setattr(
        "app.services.workflow.capability.allow_begin_step_fallback",
        lambda: True,
    )
    session = default_session()
    steps = completed_chain(through="clean", session=session)
    client = FakeClient(session=session, steps=steps)
    install_success_runners(monkeypatch)

    # New engine instance = process restart.
    engine = make_engine(client)
    from app.services.workflow.state import get_resume_state

    resume = get_resume_state("sess-e2e-1", client=client)
    assert resume["steps"]["clean"]["status"] == "completed"
    assert (resume["steps"]["clean"].get("output") or {}).get("artifacts", {}).get(
        "cleaned_artifact_key"
    )

    # Reuse clean; only finalize executes.
    reused = engine.execute_step("sess-e2e-1", "clean", user_id="user-e2e-1")
    assert reused.status == "completed"
    assert "Reused" in (reused.summary or "") or reused.artifacts.get("cleaned_artifact_key")

    result = engine.execute_step("sess-e2e-1", "finalize", user_id="user-e2e-1")
    assert result.status == "completed"
    assert client.store["data_setup_sessions"][0]["status"] == "ready"

    # Clean should not gain a new completed attempt from re-execution.
    clean_completed = [
        h for h in history_summary(client)
        if h.startswith("clean ") and "completed" in h
    ]
    assert len(clean_completed) == 1


def test_e2e07_duplicate_finalize_is_idempotent(monkeypatch):
    monkeypatch.setattr(
        "app.services.workflow.capability.allow_begin_step_fallback",
        lambda: True,
    )
    session = default_session(
        status="ready",
        output_file="sales_ready.parquet",
        dataset_version_id="dv-e2e-1",
    )
    steps = completed_chain(through="finalize", session=session)
    client = FakeClient(session=session, steps=steps)
    install_success_runners(monkeypatch)
    engine = make_engine(client)

    first = engine.execute_step("sess-e2e-1", "finalize", user_id="user-e2e-1")
    second = engine.execute_step("sess-e2e-1", "finalize", user_id="user-e2e-1")
    assert first.status == "completed"
    assert second.status == "completed"
    finalize_rows = [
        r for r in client.store["workflow_steps"] if r["step_type"] == "finalize"
    ]
    # No duplicate publish row — still a single completed finalize version.
    completed = [r for r in finalize_rows if r["status"] == "completed"]
    assert len(completed) == 1
    assert client.store["data_setup_sessions"][0]["dataset_version_id"] == "dv-e2e-1"


def test_e2e_clean_artifact_missing_rejects_reuse(monkeypatch):
    monkeypatch.setattr(
        "app.services.workflow.capability.allow_begin_step_fallback",
        lambda: True,
    )
    session = default_session()
    steps = completed_chain(through="clean", session=session)
    # Strip cleaned artifact while keeping completed status.
    for row in steps:
        if row["step_type"] == "clean":
            row["output"]["artifacts"] = {"dataset_key": "ds-e2e"}
    client = FakeClient(session=session, steps=steps)
    install_success_runners(monkeypatch)
    engine = make_engine(client)

    engine.sync_input_validity("sess-e2e-1", session=session)
    clean = [
        r for r in client.store["workflow_steps"]
        if r["step_type"] == "clean"
    ][-1]
    assert clean["status"] == "stale" or not (
        (clean.get("output") or {}).get("artifacts") or {}
    ).get("cleaned_artifact_key")

    # Engine must replan/execute rather than silently reuse invalid completed.
    result = engine.execute_step("sess-e2e-1", "clean", user_id="user-e2e-1")
    assert result.status == "completed"
    assert result.artifacts.get("cleaned_artifact_key")


def test_e2e_finalize_rebuilds_deleted_cleaned_artifact(monkeypatch):
    """A missing private artifact must rebuild clean instead of retrying finalize."""
    monkeypatch.setattr(
        "app.services.workflow.capability.allow_begin_step_fallback",
        lambda: True,
    )
    session = default_session()
    steps = completed_chain(through="clean", session=session)
    steps.append({
        **completed_chain(through="finalize", session=session)[-1],
        "status": "failed",
        "output": {},
        "error_code": "FINALIZE_EXECUTION_FAILED",
    })
    client = FakeClient(session=session, steps=steps)
    engine = make_engine(client)
    rebuilt_handle = object()

    monkeypatch.setattr(
        "app.services.workflow.artifacts.load_cleaned_artifact",
        lambda *_args, **_kwargs: None,
    )

    def clean(*, session_id, context, **_kwargs):
        context["cleaned_handle"] = rebuilt_handle
        return (
            ToolResult(
                tool="clean_data",
                status="completed",
                summary="Rebuilt cleaned artifact",
                artifacts={
                    "dataset_key": "ds-e2e",
                    "cleaned_artifact_key": f"cleaned/{session_id}/v2.parquet",
                },
            ),
            rebuilt_handle,
        )

    def finalize(*, context, **_kwargs):
        assert context["cleaned_handle"] is rebuilt_handle
        assert context["cleaned_artifact_key"].endswith("v2.parquet")
        return ToolResult(
            tool="finalize",
            status="completed",
            summary="Published rebuilt artifact",
        )

    monkeypatch.setattr("app.services.workflow.runners.run_clean_step", clean)
    monkeypatch.setattr("app.services.workflow.runners.run_finalize_step", finalize)

    result = engine.execute_step("sess-e2e-1", "finalize", user_id="user-e2e-1")

    assert result.status == "completed"
    clean_versions = [
        row for row in client.store["workflow_steps"] if row["step_type"] == "clean"
    ]
    assert clean_versions[-1]["status"] == "completed"
    assert clean_versions[-1]["version"] == 2
