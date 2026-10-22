import asyncio
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services import analysis_agent
from app.services.agent_tool_registry import AgentToolCall
from app.services.agent_session_store import AgentSession
from app.services.dataset_engine import DatasetHandle


def test_default_agent_tool_calls_do_not_keyword_force_web():
    calls = analysis_agent._default_agent_tool_calls(
        "อัตราแลก USD THB ล่าสุดเทียบกับยอดขาย",
        user_tier="plus",
        max_search_queries=3,
        max_search_sources=5,
    )
    assert [call["tool_id"] for call in calls] == ["query_data"]

    ensured = analysis_agent._ensure_live_external_web_call(
        calls,
        "ค่าเงิน USD วันนี้",
        user_tier="plus",
        max_search_queries=3,
        max_search_sources=5,
    )
    assert [call["tool_id"] for call in ensured] == ["web_search", "query_data"]


def test_dataset_capabilities_do_not_treat_numeric_ids_as_metrics():
    handle = DatasetHandle.from_dataframe(pd.DataFrame({
        "customer_id": [1001, 1002],
        "order_total": [50.0, 75.0],
        "candidate_status": ["new", "won"],
    }))
    capabilities = analysis_agent.build_dataset_tool_capabilities(
        handle,
        {"customer_id": "customer_id", "order_total": "sales"},
    )

    assert capabilities.numeric_columns == ("order_total",)
    assert capabilities.entity_columns == ("customer_id",)
    assert capabilities.identifier_columns == ("customer_id",)
    assert "candidate_status" not in capabilities.date_columns


def test_planned_tool_call_rejects_hallucinated_or_incompatible_columns():
    capabilities = analysis_agent.DatasetToolCapabilities(
        columns=("date", "sales", "region"),
        numeric_columns=("sales",),
        date_columns=("date",),
        categorical_columns=("region",),
        entity_columns=(),
    )
    eligible = {"compare_periods", "compute_metrics"}

    valid = analysis_agent.validate_planned_tool_call(
        {
            "tool_id": "compare_periods",
            "arguments": {"value_column": "sales", "date_column": "date", "grain": "month"},
            "reason": "Compare the attached dataset over time.",
        },
        eligible_ids=eligible,
        capabilities=capabilities,
    )
    hallucinated = analysis_agent.validate_planned_tool_call(
        {
            "tool_id": "compute_metrics",
            "arguments": {"column": "revenue"},
            "reason": "Column does not exist.",
        },
        eligible_ids=eligible,
        capabilities=capabilities,
    )
    wrong_type = analysis_agent.validate_planned_tool_call(
        {
            "tool_id": "compute_metrics",
            "arguments": {"column": "region"},
            "reason": "Categorical values cannot be summed.",
        },
        eligible_ids=eligible,
        capabilities=capabilities,
    )

    assert valid is not None
    assert hallucinated is None
    assert wrong_type is None


def test_tool_planner_hides_irrelevant_tools_and_drops_invalid_model_calls():
    handle = DatasetHandle.from_dataframe(pd.DataFrame({
        "sales": [10, 20],
        "region": ["north", "south"],
    }))
    captured_prompt = ""

    async def completion(**kwargs):
        nonlocal captured_prompt
        captured_prompt = kwargs["messages"][0]["content"]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=(
            '{"tool_calls":['
            '{"tool_id":"compute_metrics","arguments":{"column":"sales"},"reason":"valid"},'
            '{"tool_id":"forecast_series","arguments":{"value_column":"sales","date_column":"date"},"reason":"no date"},'
            '{"tool_id":"compute_metrics","arguments":{"column":"revenue"},"reason":"invented"}'
            ']}'
        )))])

    calls = asyncio.run(analysis_agent.plan_agent_tool_calls(
        "วิเคราะห์ภาพรวมยอดขาย",
        handle,
        "",
        "test-model",
        completion,
        user_tier="pro",
    ))

    assert [call["tool_id"] for call in calls] == ["compute_metrics"]
    available_section = captured_prompt.split("Available tools:", 1)[1]
    assert '"forecast_series"' not in available_section
    assert '"bind_chart_field"' not in available_section
    assert '"execute_dataset_join"' not in available_section


def test_tool_planner_exposes_server_side_read_only_calculator():
    handle = DatasetHandle.from_dataframe(pd.DataFrame({"sales": [10, 20]}))
    captured_prompt = ""

    async def completion(**kwargs):
        nonlocal captured_prompt
        captured_prompt = kwargs["messages"][0]["content"]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=(
            '{"tool_calls":[{"tool_id":"safe_calculator",'
            '"arguments":{"expression":"10 + 20"},"reason":"Verify a displayed total."}]}'
        )))])

    calls = asyncio.run(analysis_agent.plan_agent_tool_calls(
        "ตรวจเลข 10 + 20", handle, "", "test-model", completion, user_tier="pro"
    ))

    assert calls[0]["tool_id"] == "safe_calculator"
    assert '"safe_calculator"' in captured_prompt


def test_scenario_planner_overwrites_model_baseline_with_verified_finding():
    handle = DatasetHandle.from_dataframe(pd.DataFrame({"sales": [40, 60]}))
    session = SimpleNamespace(
        analytics_results={
            "structured_findings": [{"id": "f_sales", "metric": "sum:sales", "value": 100.0}],
        },
        file_attachment_name="sales.csv",
        connection_type=None,
        dataset_type="sales_report",
        user_clarifications=[],
    )

    async def completion(**_kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=(
            '{"tool_calls":[{"tool_id":"run_scenario","arguments":{'
            '"question":"what if revenue increases 10%",'
            '"baseline_values":{"revenue":999999}},"reason":"scenario"}]}'
        )))])

    calls = asyncio.run(analysis_agent.plan_agent_tool_calls(
        "สมมติยอดขายเพิ่มขึ้น 10% จะเป็นอย่างไร",
        handle,
        "",
        "test-model",
        completion,
        column_mapping={"sales": "sales"},
        session=session,
        user_tier="pro",
    ))

    assert calls[0]["tool_id"] == "run_scenario"
    assert calls[0]["arguments"]["baseline_values"] == {"revenue": 100.0}


def test_agent_loop_executes_typed_tool_then_observes_and_stops(monkeypatch):
    async def no_clarification(*_args, **_kwargs):
        return None

    planning_round = 0

    async def typed_plan(*_args, **_kwargs):
        nonlocal planning_round
        planning_round += 1
        if planning_round > 1:
            return []
        return [
            AgentToolCall(
                tool_id="query_data",
                arguments={"question": "calculate total sales"},
                reason="Need the governed total.",
            ).model_dump(),
            AgentToolCall(
                tool_id="query_data",
                arguments={"question": "optional product breakdown"},
                reason="Only needed if the total is insufficient.",
            ).model_dump(),
        ]

    async def fake_query(*_args, **_kwargs):
        return {
            "success": True,
            "formatted": "Verified total sales: 30",
            "rows_analyzed": 2,
        }

    async def unused_completion(**_kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content="{}")
        )])

    monkeypatch.setattr(analysis_agent, "is_complex_question", lambda _q: True)
    monkeypatch.setattr(analysis_agent, "assess_clarification_needs", no_clarification)
    monkeypatch.setattr(analysis_agent, "plan_agent_tool_calls", typed_plan)
    monkeypatch.setattr(
        "app.services.agent_tool_registry.run_question_aware_analytics",
        fake_query,
    )

    result = asyncio.run(analysis_agent.run_autonomous_agent_loop(
        pd.DataFrame({"sales": [10, 20]}),
        "วิเคราะห์ยอดขายรวมและแยกสินค้า",
        "test-model",
        unused_completion,
        "user-1",
        max_agent_steps=2,
    ))

    assert result["agent_used"] is True
    assert result["step_count"] == 1
    assert result["agent_tool_calls"][0]["tool_id"] == "query_data"
    assert result["agent_tool_calls"][0]["reason"] == "Need the governed total."
    assert result["agent_decisions"][0]["action"] == "stop"
    assert result["agent_stop_reason"] == "evidence_sufficient_or_no_new_calls"


def test_typed_metric_output_becomes_verifier_compatible_finding():
    normalized = analysis_agent.normalize_agent_tool_output(
        "compute_metrics",
        {"column": "sales", "aggregation": "sum", "dimensions": []},
        {
            "success": True,
            "metric": "sales",
            "aggregation": "sum",
            "value": 125.0,
            "rows_analyzed": 4,
        },
        row_count=4,
    )

    assert normalized["formatted"].startswith("Typed tool `compute_metrics` completed")
    assert normalized["structured_findings"][0]["value"] == 125.0
    assert normalized["structured_findings"][0]["provenance"]["source_columns"] == ["sales"]
    assert normalized["structured_findings"][0]["audit"]["details"]["server_executed"] is True


def test_replanner_replaces_remaining_plan_with_novel_tool(monkeypatch):
    session = SimpleNamespace(
        planned_tool_calls=[{
            "tool_id": "inspect_dataset",
            "arguments": {"sample_rows": 20},
            "reason": "Inspect first.",
        }],
        current_step_index=1,
        completed_steps=[{
            "tool_id": "inspect_dataset",
            "success": True,
            "formatted": "sales is numeric and order_date is a date",
            "structured_findings": [],
        }],
        analytics_results={},
        file_attachment_name="sales.csv",
        connection_type=None,
        dataset_type="sales_report",
        user_clarifications=[],
    )
    handle = DatasetHandle.from_dataframe(pd.DataFrame({
        "order_date": ["2026-01-01", "2026-02-01"],
        "sales": [10, 20],
    }))

    async def new_plan(*_args, **_kwargs):
        return [AgentToolCall(
            tool_id="compare_periods",
            arguments={"value_column": "sales", "date_column": "order_date", "grain": "month"},
            reason="The inspection supports a period comparison.",
        ).model_dump()]

    async def unused_completion(**_kwargs):
        return SimpleNamespace(choices=[])

    monkeypatch.setattr(analysis_agent, "plan_agent_tool_calls", new_plan)
    decision = asyncio.run(analysis_agent.replan_agent_after_observation(
        question="วิเคราะห์แนวโน้มยอดขาย",
        handle=handle,
        model="test",
        chat_completion_fn=unused_completion,
        column_mapping={"order_date": "date", "sales": "sales"},
        session=session,
        user_tier="pro",
        remaining_capacity=2,
    ))

    assert decision["action"] == "replan"
    assert decision["tool_calls"][0]["tool_id"] == "compare_periods"


def test_large_dataset_still_uses_schema_aware_tool_planner(monkeypatch):
    handle = DatasetHandle.from_dataframe(pd.DataFrame({"sales": [10, 20]}))
    handle._is_duckdb_primary = True
    planner_called = False

    async def typed_plan(*_args, **_kwargs):
        nonlocal planner_called
        planner_called = True
        return [AgentToolCall(
            tool_id="query_data",
            arguments={"question": "calculate total sales"},
            reason="Governed dataset query.",
        ).model_dump()]

    async def fake_query(*_args, **_kwargs):
        return {"success": True, "formatted": "Verified total: 30", "rows_analyzed": 2}

    async def unused_completion(**_kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])

    monkeypatch.setattr(analysis_agent, "is_complex_question", lambda _q: True)
    monkeypatch.setattr(analysis_agent, "plan_agent_tool_calls", typed_plan)
    monkeypatch.setattr(
        "app.services.agent_tool_registry.run_question_aware_analytics",
        fake_query,
    )

    result = asyncio.run(analysis_agent.run_autonomous_agent_loop(
        handle,
        "วิเคราะห์ยอดขายทั้งหมดและหาแนวโน้ม",
        "test-model",
        unused_completion,
        "user-large",
    ))

    assert planner_called is True
    assert result["agent_tool_calls"][0]["tool_id"] == "query_data"


def test_failed_specialized_tool_replans_to_safe_dataset_query(monkeypatch):
    planning_round = 0

    async def adaptive_plan(*_args, **_kwargs):
        nonlocal planning_round
        planning_round += 1
        if planning_round == 1:
            return [AgentToolCall(
                tool_id="forecast_series",
                arguments={"value_column": "sales", "date_column": "date", "horizon": 2},
                reason="Try the requested forecast.",
            ).model_dump()]
        if planning_round == 2:
            return [AgentToolCall(
                tool_id="query_data",
                arguments={"question": "summarize the available trend without forecasting"},
                reason="Forecast was ineligible; use governed descriptive analysis.",
            ).model_dump()]
        return []

    async def no_clarification(*_args, **_kwargs):
        return None

    async def fake_query(*_args, **_kwargs):
        return {"success": True, "formatted": "Only two periods are available.", "rows_analyzed": 2}

    async def unused_completion(**_kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])

    monkeypatch.setattr(analysis_agent, "is_complex_question", lambda _q: True)
    monkeypatch.setattr(analysis_agent, "assess_clarification_needs", no_clarification)
    monkeypatch.setattr(analysis_agent, "plan_agent_tool_calls", adaptive_plan)
    monkeypatch.setattr(
        "app.services.agent_tool_registry.run_question_aware_analytics",
        fake_query,
    )

    result = asyncio.run(analysis_agent.run_autonomous_agent_loop(
        pd.DataFrame({"date": ["2026-01-01", "2026-02-01"], "sales": [10, 20]}),
        "ช่วยคาดการณ์ยอดขายและอธิบายแนวโน้ม",
        "test-model",
        unused_completion,
        "user-recovery",
        column_mapping={"date": "date", "sales": "sales"},
        max_agent_steps=3,
    ))

    assert [call["tool_id"] for call in result["agent_tool_calls"]] == [
        "forecast_series", "query_data",
    ]
    assert result["agent_tool_calls"][0]["status"] == "completed"
    assert result["tool_id"] == "query_data"
    assert result["agent_decisions"][0]["action"] == "replan"


def test_write_tool_pauses_with_a_detailed_user_approval_request(monkeypatch):
    planning_round = 0

    async def unsafe_then_stop(*_args, **_kwargs):
        nonlocal planning_round
        planning_round += 1
        if planning_round == 1:
            return [AgentToolCall(
                tool_id="execute_dataset_join",
                arguments={
                    "left_source": "a", "right_source": "b",
                    "left_key": "id", "right_key": "id", "how": "left",
                },
                reason="Unsafe model choice without confirmation.",
            ).model_dump()]
        return []

    async def no_clarification(*_args, **_kwargs):
        return None

    async def fake_query(*_args, **_kwargs):
        return {"success": True, "formatted": "Read-only recovery completed.", "rows_analyzed": 2}

    async def unused_completion(**_kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])

    monkeypatch.setattr(analysis_agent, "is_complex_question", lambda _q: True)
    monkeypatch.setattr(analysis_agent, "assess_clarification_needs", no_clarification)
    monkeypatch.setattr(analysis_agent, "plan_agent_tool_calls", unsafe_then_stop)
    monkeypatch.setattr(
        "app.services.agent_tool_registry.run_question_aware_analytics",
        fake_query,
    )

    result = asyncio.run(analysis_agent.run_autonomous_agent_loop(
        pd.DataFrame({"id": [1, 2], "sales": [10, 20]}),
        "วิเคราะห์ข้อมูลแบบปลอดภัย",
        "test-model",
        unused_completion,
        "user-rejected",
        user_tier="pro",
        max_agent_steps=3,
    ))

    assert result.reason == "tool_approval_required"
    assert "Execute Dataset Join" in result.question
    assert "Unsafe model choice without confirmation." in result.question
    assert "left_source" in result.question


def test_resume_fails_closed_when_dataset_fingerprint_changes():
    handle = DatasetHandle.from_dataframe(pd.DataFrame({"sales": [10, 20]}))
    handle._source_fingerprint = "new-source"
    session = AgentSession(
        session_id="session-mismatch",
        user_id="user-1",
        status="paused",
        original_question="ยอดขายรวมเท่าไหร่",
        source_fingerprint="old-source",
    )

    async def unused_completion(**_kwargs):
        return SimpleNamespace(choices=[])

    with pytest.raises(Exception, match="AGENT_DATASET_CONTEXT_CHANGED"):
        asyncio.run(analysis_agent.run_autonomous_agent_loop(
            handle,
            session.original_question,
            "test-model",
            unused_completion,
            session.user_id,
            session=session,
            clarification_answer="sales",
        ))
