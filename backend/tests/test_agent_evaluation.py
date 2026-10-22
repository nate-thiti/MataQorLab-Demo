import asyncio
from types import SimpleNamespace

from app.services.agent_evaluation import (
    AgentEvaluationCase,
    evaluate_agent_trace,
    run_agent_evaluation_suite,
)
from app.services.analysis_agent import assess_agent_progress


def test_evaluation_passes_grounded_expected_tool_trace():
    case = AgentEvaluationCase(
        case_id="sales_total",
        question="ยอดขายรวมเท่าไหร่",
        expected_tools=["query_data"],
        forbidden_tools=["web_search"],
        require_numeric_grounding=True,
    )
    result = evaluate_agent_trace(
        case,
        planned_calls=[{
            "tool_id": "query_data",
            "arguments": {"question": case.question},
        }],
        execution_records=[{
            "tool_id": "query_data",
            "status": "completed",
        }],
        verification={
            "status": "grounded",
            "unmatched_dataset_numeric_claims": [],
        },
    )

    assert result.passed is True
    assert result.score == 1


def test_evaluation_fails_unknown_or_ungrounded_behavior():
    case = AgentEvaluationCase(
        case_id="bad_trace",
        question="ยอดขายรวมเท่าไหร่",
        expected_tools=["query_data"],
        forbidden_tools=["python_exec"],
        max_tool_calls=1,
        require_numeric_grounding=True,
    )
    result = evaluate_agent_trace(
        case,
        planned_calls=[{"tool_id": "python_exec", "arguments": {}}],
        execution_records=[
            {"tool_id": "python_exec", "status": "completed"},
            {"tool_id": "python_exec", "status": "completed"},
        ],
        verification={
            "status": "needs_review",
            "unmatched_dataset_numeric_claims": ["999"],
        },
    )

    assert result.passed is False
    assert "expected_tools_selected" in result.errors
    assert "forbidden_tools_avoided" in result.errors
    assert "tool_call_budget_respected" in result.errors
    assert "numeric_claims_grounded" in result.errors


def test_evaluation_suite_reports_pass_rate():
    cases = [
        AgentEvaluationCase(case_id="a", question="a", expected_tools=["query_data"]),
        AgentEvaluationCase(case_id="b", question="b", expected_tools=["web_search"]),
    ]

    async def runner(case):
        tool_id = "query_data"
        return {
            "planned_calls": [{"tool_id": tool_id, "arguments": {}}],
            "execution_records": [{"tool_id": tool_id, "status": "completed"}],
        }

    summary = asyncio.run(run_agent_evaluation_suite(cases, runner))

    assert summary.passed is False
    assert summary.pass_rate == 0.5


def test_agent_progress_can_stop_after_observing_sufficient_tool_evidence():
    async def completion(**_kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"action":"stop","reason":"evidence sufficient"}')
        )])

    decision = asyncio.run(assess_agent_progress(
        original_question="ยอดขายรวมเท่าไหร่",
        completed_steps=[{
            "tool_id": "query_data",
            "success": True,
            "formatted": "Verified total sales: 100",
        }],
        remaining_calls=[{
            "tool_id": "query_data",
            "reason": "optional breakdown",
        }],
        model="test",
        chat_completion_fn=completion,
    ))

    assert decision == {"action": "stop", "reason": "evidence sufficient"}
