"""Pytest fixtures shared across backend tests."""
import inspect
import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-llm-key")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

from app.core.config import settings


@pytest.fixture(autouse=True)
def writable_agent_session_dir(tmp_path, monkeypatch):
    """Isolate agent session file I/O from Docker/root-owned data/agent_sessions."""
    session_dir = tmp_path / "agent_sessions"
    session_dir.mkdir()
    monkeypatch.setattr(settings, "AGENT_SESSION_DIR", str(session_dir))


@pytest.fixture
def inline_asyncio_to_thread(monkeypatch):
    """Run deterministic test doubles inline without a default executor.

    Python 3.12.3 can wait indefinitely while ``asyncio.run`` shuts down an
    executor, which turns otherwise-completed orchestrator tests into hangs.
    """
    import asyncio

    async def run_sync(func, *args, **kwargs):
        result = func(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    monkeypatch.setattr(asyncio, "to_thread", run_sync)
