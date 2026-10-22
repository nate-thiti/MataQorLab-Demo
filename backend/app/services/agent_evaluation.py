"""Deterministic evaluation harness for agent plans, calls, and grounding."""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field


class AgentEvaluationCase(BaseModel):
    case_id: str
    question: str
    expected_tools: List[str] = Field(default_factory=list)
    forbidden_tools: List[str] = Field(default_factory=list)
    max_tool_calls: int = 5
    require_completed_tool: bool = True
    require_numeric_grounding: bool = False


class AgentEvaluationResult(BaseModel):
    case_id: str
    passed: bool
    score: float
    checks: Dict[str, bool]
    errors: List[str] = Field(default_factory=list)
    observed_tools: List[str] = Field(default_factory=list)


class AgentEvaluationSummary(BaseModel):
    passed: bool
    pass_rate: float
    average_score: float
    results: List[AgentEvaluationResult]


GOLDEN_AGENT_CASES: List[AgentEvaluationCase] = [
    AgentEvaluationCase(
        case_id="dataset_total",
        question="ยอดขายรวมเท่าไหร่",
        expected_tools=["query_data"],
        forbidden_tools=["safe_calculator", "web_search"],
        require_numeric_grounding=True,
    ),
    AgentEvaluationCase(
        case_id="current_external_comparison",
        question="เทียบยอดขายของเรากับแนวโน้มตลาดล่าสุด",
        expected_tools=["query_data", "web_search"],
        require_numeric_grounding=True,
    ),
    AgentEvaluationCase(
        case_id="explicit_arithmetic",
        question="20% ของ 50 เท่ากับเท่าไหร่",
        expected_tools=["safe_calculator"],
        forbidden_tools=["query_data", "web_search"],
        require_numeric_grounding=True,
    ),
    AgentEvaluationCase(
        case_id="tool_failure_fail_closed",
        question="สรุปตัวเลขจากข้อมูลนี้",
        expected_tools=["query_data"],
        require_completed_tool=False,
        require_numeric_grounding=False,
    ),
]


def evaluate_agent_trace(
    case: AgentEvaluationCase,
    *,
    planned_calls: Sequence[Dict[str, Any]],
    execution_records: Sequence[Dict[str, Any]],
    verification: Optional[Dict[str, Any]] = None,
) -> AgentEvaluationResult:
    """Score tool selection, bounds, completion, and numeric grounding."""
    planned_tools = [str(item.get("tool_id") or "") for item in planned_calls]
    executed_tools = [str(item.get("tool_id") or "") for item in execution_records]
    observed = executed_tools or planned_tools
    expected = set(case.expected_tools)
    forbidden = set(case.forbidden_tools)
    completed = [
        item for item in execution_records
        if item.get("status") in {"completed", "cached"}
    ]
    verification = verification or {}

    checks = {
        "expected_tools_selected": expected.issubset(set(observed)),
        "forbidden_tools_avoided": not forbidden.intersection(observed),
        "tool_call_budget_respected": len(execution_records) <= case.max_tool_calls,
        "registered_shape_only": all(
            bool(item.get("tool_id")) and isinstance(item.get("arguments", {}), dict)
            for item in planned_calls
        ),
        "required_tool_completed": bool(completed) if case.require_completed_tool else True,
        "numeric_claims_grounded": (
            verification.get("status") == "grounded"
            and not verification.get("unmatched_dataset_numeric_claims")
            if case.require_numeric_grounding
            else True
        ),
    }
    errors = [name for name, passed in checks.items() if not passed]
    score = sum(1 for passed in checks.values() if passed) / len(checks)
    return AgentEvaluationResult(
        case_id=case.case_id,
        passed=not errors,
        score=round(score, 4),
        checks=checks,
        errors=errors,
        observed_tools=observed,
    )


async def run_agent_evaluation_suite(
    cases: Sequence[AgentEvaluationCase],
    runner: Callable[[AgentEvaluationCase], Awaitable[Dict[str, Any]]],
) -> AgentEvaluationSummary:
    """Run cases through an injected agent runner; suitable for CI or staging."""
    results: List[AgentEvaluationResult] = []
    for case in cases:
        trace = await runner(case)
        results.append(evaluate_agent_trace(
            case,
            planned_calls=trace.get("planned_calls") or [],
            execution_records=trace.get("execution_records") or [],
            verification=trace.get("verification"),
        ))
    pass_rate = sum(1 for item in results if item.passed) / len(results) if results else 1.0
    average_score = sum(item.score for item in results) / len(results) if results else 1.0
    return AgentEvaluationSummary(
        passed=all(item.passed for item in results),
        pass_rate=round(pass_rate, 4),
        average_score=round(average_score, 4),
        results=results,
    )
