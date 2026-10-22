import asyncio

import pandas as pd
import pytest

from app.services.agent_tool_registry import (
    AGENT_TOOL_REGISTRY,
    AgentToolBudget,
    AgentToolCall,
    AgentToolContext,
    AgentToolDefinition,
    AgentToolDispatcher,
    EmptyInput,
    ToolBudgetExceeded,
    ToolPermissionError,
    ToolTransientError,
    UnknownAgentToolError,
    list_agent_tools,
)
from app.services.dataset_engine import as_handle


def _context(**overrides):
    values = {
        "user_id": "user-1",
        "user_tier": "free",
        "handle": as_handle(pd.DataFrame({"sales": [10, 20]})),
        "model": "test",
        "chat_completion_fn": None,
    }
    values.update(overrides)
    return AgentToolContext(**values)


def test_registry_exposes_typed_server_owned_contracts():
    tools = {item["tool_id"]: item for item in list_agent_tools()}

    assert {"query_data", "safe_calculator", "web_search"}.issubset(tools)
    assert {"inspect", "prepare", "map", "validate", "clean", "finalize"}.issubset(tools)
    assert tools["query_data"]["authority"].startswith("question_analytics")
    assert tools["query_data"]["input_schema"]["additionalProperties"] is False
    assert tools["clean"]["side_effect"] == "write"
    assert tools["run_python_analysis"]["requires_confirmation"] is True
    assert tools["run_python_analysis"]["execution_environment"] == "external_sandbox"
    assert tools["execute_dataset_join"]["requires_confirmation"] is True
    assert "compute_metrics" in tools
    assert {"list_chart_fields", "add_chart", "rename_chart", "bind_chart_field", "inspect_chart"}.issubset(tools)
    assert tools["bind_chart_field"]["authority"] == "chart_builder.bind_chart_field"


def test_dispatcher_validates_executes_and_idempotently_reuses_result():
    async def scenario():
        dispatcher = AgentToolDispatcher()
        budget = AgentToolBudget(max_calls=1, max_cost_units=1)
        call = AgentToolCall(
            tool_id="safe_calculator",
            arguments={"expression": "20% of 50"},
            reason="Explicit arithmetic requires a server calculator.",
        )

        first = await dispatcher.execute(call, context=_context(), budget=budget)
        second = await dispatcher.execute(call, context=_context(), budget=budget)

        assert first.record.status == "completed"
        assert first.output["result"] == 10
        assert first.record.reason.startswith("Explicit arithmetic")
        assert second.record.status == "cached"
        assert second.record.cost_units == 0
        assert budget.calls_used == 1

    asyncio.run(scenario())


def test_dispatcher_fails_closed_for_unknown_tool_and_tier():
    async def scenario():
        dispatcher = AgentToolDispatcher()
        budget = AgentToolBudget(max_calls=2, max_cost_units=4)
        with pytest.raises(UnknownAgentToolError):
            await dispatcher.execute(
                {"tool_id": "python_exec", "arguments": {}},
                context=_context(),
                budget=budget,
            )
        with pytest.raises(ToolPermissionError):
            await dispatcher.execute(
                {"tool_id": "web_search", "arguments": {"query": "latest GDP"}},
                context=_context(user_tier="free"),
                budget=budget,
            )

    asyncio.run(scenario())


def test_dispatcher_enforces_call_and_cost_budget():
    async def scenario():
        dispatcher = AgentToolDispatcher()
        budget = AgentToolBudget(max_calls=0, max_cost_units=0)
        with pytest.raises(ToolBudgetExceeded):
            await dispatcher.execute(
                {"tool_id": "safe_calculator", "arguments": {"expression": "1+1"}},
                context=_context(),
                budget=budget,
            )

    asyncio.run(scenario())


def test_dispatcher_retries_transient_failure(monkeypatch):
    calls = 0

    async def flaky(_args, _context):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ToolTransientError("try again")
        return {"success": True}

    definition = AgentToolDefinition(
        tool_id="test_retry",
        name="Retry Test",
        description="test",
        category="utility",
        input_model=EmptyInput,
        handler=flaky,
        authority="test",
        max_retries=1,
    )
    monkeypatch.setitem(AGENT_TOOL_REGISTRY, definition.tool_id, definition)

    async def scenario():
        result = await AgentToolDispatcher().execute(
            {"tool_id": "test_retry", "arguments": {}},
            context=_context(),
            budget=AgentToolBudget(max_calls=1, max_cost_units=1),
        )
        assert result.record.status == "completed"
        assert result.record.attempts == 2

    asyncio.run(scenario())


def test_dispatcher_times_out_bounded_tool(monkeypatch):
    async def slow(_args, _context):
        await asyncio.sleep(0.05)
        return {"success": True}

    definition = AgentToolDefinition(
        tool_id="test_timeout",
        name="Timeout Test",
        description="test",
        category="utility",
        input_model=EmptyInput,
        handler=slow,
        authority="test",
        timeout_seconds=0.001,
    )
    monkeypatch.setitem(AGENT_TOOL_REGISTRY, definition.tool_id, definition)

    async def scenario():
        result = await AgentToolDispatcher().execute(
            {"tool_id": "test_timeout", "arguments": {}},
            context=_context(),
            budget=AgentToolBudget(max_calls=1, max_cost_units=1),
        )
        assert result.record.status == "timed_out"
        assert result.record.error_code == "TOOL_TIMEOUT"

    asyncio.run(scenario())


def test_dispatcher_rejects_confirmation_required_tool_without_approved_action(monkeypatch):
    definition = AgentToolDefinition(
        tool_id="test_confirmed_write", name="Confirmed", description="test",
        category="utility", input_model=EmptyInput,
        handler=lambda _args, _context: {"success": True}, authority="test",
        side_effect="write", requires_confirmation=True,
    )
    monkeypatch.setitem(AGENT_TOOL_REGISTRY, definition.tool_id, definition)

    async def scenario():
        with pytest.raises(ToolPermissionError, match="TOOL_CONFIRMATION_REQUIRED"):
            await AgentToolDispatcher().execute(
                {"tool_id": definition.tool_id, "arguments": {}},
                context=_context(), budget=AgentToolBudget(max_calls=1, max_cost_units=1),
            )
        result = await AgentToolDispatcher().execute(
            {"tool_id": definition.tool_id, "arguments": {}, "approved_action_id": "approved-1"},
            context=_context(approved_action_ids=frozenset({"approved-1"})),
            budget=AgentToolBudget(max_calls=1, max_cost_units=1),
        )
        assert result.record.status == "completed"

    asyncio.run(scenario())


def test_core_bi_tools_compute_full_dataset_metrics_and_periods():
    context = _context(handle=as_handle(pd.DataFrame({
        "date": ["2026-01-01", "2026-01-20", "2026-02-01"],
        "sales": [10, 20, 40],
        "segment": ["A", "A", "B"],
    })))

    async def scenario():
        dispatcher = AgentToolDispatcher()
        metric = await dispatcher.execute(
            {"tool_id": "compute_metrics", "arguments": {"column": "sales", "aggregation": "sum"}},
            context=context, budget=AgentToolBudget(max_calls=1, max_cost_units=2),
        )
        periods = await dispatcher.execute(
            {"tool_id": "compare_periods", "arguments": {
                "value_column": "sales", "date_column": "date", "grain": "month",
            }},
            context=context, budget=AgentToolBudget(max_calls=1, max_cost_units=2),
        )
        assert metric.output["value"] == 70
        assert metric.output["sampled"] is False
        assert periods.output["delta"] == 10
        assert periods.output["sampled"] is False

    asyncio.run(scenario())


def test_chart_field_tools_bind_and_inspect_without_persisting():
    context = _context(handle=as_handle(pd.DataFrame({
        "branch": ["North", "South"],
        "revenue": [10, 25],
    })))

    async def scenario():
        dispatcher = AgentToolDispatcher()
        fields = await dispatcher.execute(
            {"tool_id": "list_chart_fields", "arguments": {}},
            context=context, budget=AgentToolBudget(max_calls=1, max_cost_units=2),
        )
        created = await dispatcher.execute(
            {"tool_id": "add_chart", "arguments": {"chart_type": "bar", "title": "Branch revenue"}},
            context=context, budget=AgentToolBudget(max_calls=1, max_cost_units=2),
        )
        bound = await dispatcher.execute(
            {
                "tool_id": "bind_chart_field",
                "arguments": {
                    "widget": created.output["widget"],
                    "well": "y",
                    "column": "revenue",
                    "aggregation": "sum",
                },
            },
            context=context, budget=AgentToolBudget(max_calls=1, max_cost_units=2),
        )
        renamed = await dispatcher.execute(
            {
                "tool_id": "rename_chart",
                "arguments": {
                    "widget": bound.output["widget"],
                    "title": "Revenue by branch",
                },
            },
            context=context, budget=AgentToolBudget(max_calls=1, max_cost_units=2),
        )
        inspected = await dispatcher.execute(
            {"tool_id": "inspect_chart", "arguments": {"widget": renamed.output["widget"]}},
            context=context, budget=AgentToolBudget(max_calls=1, max_cost_units=2),
        )
        assert "branch" in [item["name"] for item in fields.output["dimensions"]]
        assert created.output["widget"]["title"] == "Branch revenue"
        assert bound.output["widget"]["title"] == "Branch revenue"
        assert renamed.output["widget"]["title"] == "Revenue by branch"
        assert bound.output["inspect"]["formula"] == "SUM(revenue) GROUP BY branch"
        assert inspected.output["engine"] == "duckdb"
        assert inspected.output["wells"]["y"]["field"] == "revenue"

    asyncio.run(scenario())
