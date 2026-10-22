import asyncio
from types import SimpleNamespace

import pytest

from app.services.analysis_agent import AgentLLMLimitExceeded, _wrap_llm_budget


def test_agent_llm_budget_exposes_remaining_calls():
    async def scenario():
        calls = 0

        async def completion(**_kwargs):
            nonlocal calls
            calls += 1
            return SimpleNamespace()

        limited = _wrap_llm_budget(completion, 2)

        assert limited.remaining_calls() == 2
        await limited(model="test", messages=[])
        assert limited.remaining_calls() == 1
        await limited(model="test", messages=[])
        assert limited.remaining_calls() == 0
        assert calls == 2
        with pytest.raises(AgentLLMLimitExceeded):
            await limited(model="test", messages=[])

    asyncio.run(scenario())
