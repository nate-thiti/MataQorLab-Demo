"""E2E-05 — tool failure + retry with attempt history preserved."""
from __future__ import annotations

from .helpers import (
    FakeClient,
    completed_chain,
    default_session,
    history_summary,
    install_success_runners,
    make_engine,
)


def test_e2e05_clean_failure_then_retry_preserves_history(monkeypatch):
    monkeypatch.setattr(
        "app.services.workflow.capability.allow_begin_step_fallback",
        lambda: True,
    )
    session = default_session()
    client = FakeClient(
        session=session,
        steps=completed_chain(through="validate", session=session),
    )
    install_success_runners(monkeypatch, fail_steps={"clean": 1})
    engine = make_engine(client)

    try:
        engine.execute_step("sess-e2e-1", "clean", user_id="user-e2e-1")
        assert False, "expected clean failure"
    except RuntimeError as exc:
        assert "forced failure" in str(exc)

    # Upstream remains completed.
    hist = history_summary(client)
    assert any(h.startswith("validate v1 attempt1 completed") for h in hist)
    assert any("clean" in h and "failed" in h for h in hist)

    # Retry via engine API (same logical version, attempt bump via begin_step).
    result = engine.retry_step("sess-e2e-1", "clean", user_id="user-e2e-1")
    assert result.status == "completed"

    hist = history_summary(client)
    clean_lines = [h for h in hist if h.startswith("clean ")]
    assert any("failed" in h for h in clean_lines)
    assert any("completed" in h for h in clean_lines)
    # History must not be overwritten to a single row.
    assert len(clean_lines) >= 2

    engine.execute_step("sess-e2e-1", "finalize", user_id="user-e2e-1")
    assert client.store["data_setup_sessions"][0]["status"] == "ready"
