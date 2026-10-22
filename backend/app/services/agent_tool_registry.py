"""Typed, server-owned tool registry and reliable dispatcher for AI agents.

The model may select a registered ``tool_id`` and provide arguments, but it
never receives a Python callable and never executes SQL or arithmetic itself.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Literal, Optional, Type

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.services.calculator import calculate_from_question
from app.services.dataset_engine import DatasetHandle, _quote_ident
from app.services.question_analytics import run_question_aware_analytics
from app.services.web_search import run_multi_web_search
from app.services.analytical_extensions import (
    assess_join_cardinality,
    forecast_metric,
    infer_grain_and_join_risks,
    parse_and_run_scenario,
)
from app.services.decision_assurance import (
    build_causal_eligibility,
    run_causal_analyses,
)
from app.services.semantic_mapping_gate import evaluate_semantic_mapping_gate


ToolCategory = Literal["data_setup", "analytics", "external_context", "utility"]
ToolSideEffect = Literal["read", "write"]
ToolExecutionEnvironment = Literal["server", "external_sandbox"]
ToolCallStatus = Literal["completed", "failed", "timed_out", "cancelled", "cached"]


class AgentToolError(RuntimeError):
    """Base class for bounded, user-safe tool failures."""


class UnknownAgentToolError(AgentToolError):
    pass


class ToolPermissionError(AgentToolError):
    pass


class ToolBudgetExceeded(AgentToolError):
    pass


class ToolTransientError(AgentToolError):
    """A failure that a tool definition may retry."""


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatasetQueryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2_000)
    max_llm_attempts: int = Field(default=1, ge=1, le=2)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class WebSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    max_queries: int = Field(default=3, ge=1, le=5)
    max_sources: int = Field(default=8, ge=1, le=20)


class CalculatorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expression: str = Field(min_length=1, max_length=200)


class ServerClockInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: str = Field(default="th", max_length=16)


class SetupStepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    force_new_version: bool = False


class DatasetInspectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_rows: int = Field(default=20, ge=0, le=100)


class MetricInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str = Field(min_length=1, max_length=300)
    aggregation: Literal["sum", "average", "min", "max", "count", "distinct_count"] = "sum"
    dimensions: List[str] = Field(default_factory=list, max_length=3)
    limit: int = Field(default=20, ge=1, le=100)


class PeriodComparisonInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value_column: str = Field(min_length=1, max_length=300)
    date_column: str = Field(min_length=1, max_length=300)
    grain: Literal["day", "week", "month", "quarter", "year"] = "month"


class SegmentComparisonInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value_column: str = Field(min_length=1, max_length=300)
    segment_column: str = Field(min_length=1, max_length=300)
    aggregation: Literal["sum", "average", "count"] = "sum"
    limit: int = Field(default=20, ge=2, le=100)


class ColumnsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    columns: List[str] = Field(default_factory=list, max_length=100)


class DistributionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str = Field(min_length=1, max_length=300)


class RelationshipInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x_column: str = Field(min_length=1, max_length=300)
    y_column: str = Field(min_length=1, max_length=300)


class ForecastInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value_column: str = Field(min_length=1, max_length=300)
    date_column: str = Field(min_length=1, max_length=300)
    horizon: int = Field(default=3, ge=1, le=24)


class ScenarioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)
    baseline_values: Dict[str, float] = Field(default_factory=dict)


class CohortInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_column: str = Field(min_length=1, max_length=300)
    date_column: str = Field(min_length=1, max_length=300)


class CausalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    design: Dict[str, Any] = Field(default_factory=dict)


class ExplainEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_ids: List[str] = Field(default_factory=list, max_length=50)


class JoinPlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left_source: str = Field(min_length=1, max_length=300)
    right_source: str = Field(min_length=1, max_length=300)
    left_key: str = Field(min_length=1, max_length=300)
    right_key: str = Field(min_length=1, max_length=300)
    how: Literal["inner", "left"] = "left"


class DaxExpressionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(min_length=1, max_length=4000)


class DaxDefinitionInput(DaxExpressionInput):
    dataset_key: str = Field(min_length=1, max_length=500)
    name: str = Field(min_length=1, max_length=120)
    label: Optional[str] = Field(default=None, max_length=120)


class PythonCodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=100000)
    packages: List[str] = Field(default_factory=list, max_length=20)


class PythonProposalInput(PythonCodeInput):
    dataset_key: str = Field(min_length=1, max_length=500)
    dataset_version_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_outputs: List[str] = Field(default_factory=list, max_length=10)


class PythonJobInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str = Field(min_length=1, max_length=80)
    approval_id: Optional[str] = Field(default=None, max_length=200)


class AddChartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chart_type: Literal["bar", "line", "area", "pie", "pareto"] = "bar"
    title: Optional[str] = Field(default=None, max_length=160)


class RenameChartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    widget: Dict[str, Any]
    title: str = Field(min_length=1, max_length=160)


class ChartWidgetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    widget: Dict[str, Any]


class BindChartFieldInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    widget: Dict[str, Any]
    well: Literal["axis", "values", "x", "y"]
    column: str = Field(min_length=1, max_length=300)
    aggregation: Optional[Literal["sum", "average", "count"]] = None


@dataclass
class AgentToolContext:
    user_id: str
    user_tier: str = "free"
    handle: Optional[DatasetHandle] = None
    model: str = ""
    chat_completion_fn: Optional[Callable[..., Awaitable[Any]]] = None
    column_mapping: Optional[Dict[str, str]] = None
    workflow_engine: Any = None
    approved_action_ids: frozenset[str] = frozenset()
    analytics_results: Optional[Dict[str, Any]] = None
    data_contract: Optional[Dict[str, Any]] = None
    data_sources: Dict[str, DatasetHandle] = field(default_factory=dict)
    conversation_id: Optional[str] = None


ToolHandler = Callable[[BaseModel, AgentToolContext], Awaitable[Dict[str, Any]] | Dict[str, Any]]


@dataclass(frozen=True)
class AgentToolDefinition:
    tool_id: str
    name: str
    description: str
    category: ToolCategory
    input_model: Type[BaseModel]
    handler: ToolHandler
    authority: str
    side_effect: ToolSideEffect = "read"
    timeout_seconds: float = 30.0
    max_retries: int = 0
    cost_units: int = 1
    idempotent: bool = True
    requires_dataset: bool = False
    allowed_tiers: tuple[str, ...] = ("free", "plus", "pro", "premium")
    requires_confirmation: bool = False
    execution_environment: ToolExecutionEnvironment = "server"
    output_schema: Dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    retryable_exceptions: tuple[type[BaseException], ...] = (
        TimeoutError,
        ConnectionError,
        ToolTransientError,
    )

    def public_dict(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "authority": self.authority,
            "side_effect": self.side_effect,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "cost_units": self.cost_units,
            "idempotent": self.idempotent,
            "requires_dataset": self.requires_dataset,
            "allowed_tiers": list(self.allowed_tiers),
            "requires_confirmation": self.requires_confirmation,
            "execution_environment": self.execution_environment,
            "output_schema": self.output_schema,
            "input_schema": self.input_model.model_json_schema(),
        }


class AgentToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_id: str = Field(min_length=1, max_length=80)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="", max_length=500)
    idempotency_key: Optional[str] = Field(default=None, max_length=160)
    approved_action_id: Optional[str] = Field(default=None, max_length=200)


class AgentToolCallRecord(BaseModel):
    call_id: str
    tool_id: str
    status: ToolCallStatus
    reason: str = ""
    attempts: int = 0
    duration_ms: int = 0
    cost_units: int = 0
    idempotency_key: str
    input_hash: str
    output_summary: Dict[str, Any] = Field(default_factory=dict)
    error_code: Optional[str] = None
    error: Optional[str] = None
    started_at: str
    completed_at: str


@dataclass
class AgentToolDispatchResult:
    record: AgentToolCallRecord
    output: Optional[Dict[str, Any]] = None


@dataclass
class AgentToolBudget:
    max_calls: int
    max_cost_units: int
    calls_used: int = 0
    cost_units_used: int = 0

    def reserve(self, definition: AgentToolDefinition) -> None:
        if self.calls_used + 1 > self.max_calls:
            raise ToolBudgetExceeded("TOOL_CALL_BUDGET_EXCEEDED")
        if self.cost_units_used + definition.cost_units > self.max_cost_units:
            raise ToolBudgetExceeded("TOOL_COST_BUDGET_EXCEEDED")
        self.calls_used += 1
        self.cost_units_used += definition.cost_units


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bounded_output_summary(output: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not output:
        return {}
    sources = output.get("web_sources") or []
    semantic_success = output.get("success", output.get("eligible", True))
    return {
        "success": semantic_success is not False,
        "eligible": output.get("eligible"),
        "reason": str(output.get("reason") or "")[:240] or None,
        "engine": output.get("engine") or output.get("question_aware", {}).get("engine"),
        "rows_analyzed": output.get("rows_analyzed"),
        "source_count": len(sources),
        "has_result": bool(output),
    }


async def _query_data(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, DatasetQueryInput)
    if context.handle is None or context.chat_completion_fn is None:
        raise ToolPermissionError("DATASET_CONTEXT_REQUIRED")
    result = await run_question_aware_analytics(
        context.handle,
        args.question,
        context.model,
        context.chat_completion_fn,
        context.column_mapping,
        max_llm_attempts=args.max_llm_attempts,
    )
    if not isinstance(result, dict):
        raise AgentToolError("INVALID_DATASET_TOOL_RESULT")
    return result


async def _web_search(args: BaseModel, _context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, WebSearchInput)
    result = await asyncio.to_thread(
        run_multi_web_search,
        args.query,
        max_queries=args.max_queries,
        max_sources=args.max_sources,
    )
    if not isinstance(result, dict):
        raise AgentToolError("INVALID_WEB_TOOL_RESULT")
    return result


async def _calculator(args: BaseModel, _context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, CalculatorInput)
    result = calculate_from_question(args.expression)
    if not result:
        raise AgentToolError("UNSUPPORTED_CALCULATION")
    return result


async def _server_clock(args: BaseModel, _context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, ServerClockInput)
    from app.services.server_clock import build_server_clock_tool_result

    return build_server_clock_tool_result(locale=args.locale or "th")


def _setup_handler(step_type: str) -> ToolHandler:
    async def execute(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
        assert isinstance(args, SetupStepInput)
        if context.workflow_engine is None:
            raise ToolPermissionError("WORKFLOW_ENGINE_REQUIRED")
        result = await asyncio.to_thread(
            context.workflow_engine.execute_step,
            args.session_id,
            step_type,
            user_id=context.user_id,
            force_new_version=args.force_new_version,
        )
        if hasattr(result, "to_public_dict"):
            return result.to_public_dict()
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if isinstance(result, dict):
            return result
        raise AgentToolError("INVALID_SETUP_TOOL_RESULT")

    return execute


def _dataset(context: AgentToolContext) -> DatasetHandle:
    if context.handle is None:
        raise ToolPermissionError("DATASET_CONTEXT_REQUIRED")
    return context.handle


def _column(frame: pd.DataFrame, name: str) -> pd.Series:
    if name not in frame.columns:
        raise AgentToolError(f"UNKNOWN_DATASET_COLUMN:{name}")
    return frame[name]


def _sample(context: AgentToolContext, limit: int = 200_000) -> tuple[DatasetHandle, pd.DataFrame]:
    handle = _dataset(context)
    return handle, handle.to_pandas(limit=min(handle.row_count(), limit))


async def _inspect_dataset(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, DatasetInspectInput)
    handle = _dataset(context)
    summary = handle.summarize_df().replace({np.nan: None}).to_dict(orient="records")
    sample = handle.to_pandas(limit=args.sample_rows).replace({np.nan: None})
    return {
        "success": True,
        "row_count": handle.row_count(),
        "columns": handle.column_names(),
        "column_summary": summary,
        "sample_rows": sample.to_dict(orient="records"),
        "grain_assessment": infer_grain_and_join_risks(handle, context.column_mapping),
    }


async def _compute_metrics(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, MetricInput)
    handle = _dataset(context)
    available = set(handle.column_names())
    if args.column not in available:
        raise AgentToolError(f"UNKNOWN_DATASET_COLUMN:{args.column}")
    dimensions = list(dict.fromkeys(args.dimensions))
    for dimension in dimensions:
        if dimension not in available:
            raise AgentToolError(f"UNKNOWN_DATASET_COLUMN:{dimension}")
    value_sql = _quote_ident(args.column)
    aggregate = {
        "sum": f"SUM(TRY_CAST({value_sql} AS DOUBLE))",
        "average": f"AVG(TRY_CAST({value_sql} AS DOUBLE))",
        "min": f"MIN(TRY_CAST({value_sql} AS DOUBLE))",
        "max": f"MAX(TRY_CAST({value_sql} AS DOUBLE))",
        "count": f"COUNT({value_sql})",
        "distinct_count": f"COUNT(DISTINCT {value_sql})",
    }[args.aggregation]
    if dimensions:
        dimension_sql = ", ".join(_quote_ident(item) for item in dimensions)
        frame = handle.execute_select(
            f"SELECT {dimension_sql}, {aggregate} AS value FROM df "
            f"GROUP BY {dimension_sql} ORDER BY value DESC NULLS LAST LIMIT {args.limit}",
            max_rows=args.limit,
        )
        rows = frame.replace({np.nan: None}).to_dict(orient="records")
        value: Any = None
    else:
        frame = handle.execute_select(f"SELECT {aggregate} AS value FROM df", max_rows=2)
        raw = None if frame.empty else frame.iloc[0, 0]
        value = None if pd.isna(raw) else float(raw)
        rows = []
    return {
        "success": True, "metric": args.column, "aggregation": args.aggregation,
        "value": value, "rows": rows, "rows_analyzed": handle.row_count(),
        "total_rows": handle.row_count(), "sampled": False,
        "provenance": {"engine": "duckdb", "source_columns": [args.column, *dimensions]},
    }


async def _compare_periods(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, PeriodComparisonInput)
    handle = _dataset(context)
    available = set(handle.column_names())
    if args.value_column not in available or args.date_column not in available:
        raise AgentToolError("UNKNOWN_DATASET_COLUMN")
    value_sql, date_sql = _quote_ident(args.value_column), _quote_ident(args.date_column)
    frame = handle.execute_select(
        f"SELECT CAST(DATE_TRUNC('{args.grain}', TRY_CAST({date_sql} AS TIMESTAMP)) AS VARCHAR) AS period, "
        f"SUM(TRY_CAST({value_sql} AS DOUBLE)) AS value FROM df "
        f"WHERE TRY_CAST({date_sql} AS TIMESTAMP) IS NOT NULL "
        "GROUP BY 1 ORDER BY 1 DESC LIMIT 100",
        max_rows=100,
    ).sort_values("period")
    rows = [{"period": str(row.period), "value": float(row.value)} for row in frame.itertuples()]
    latest = rows[-1] if rows else None
    previous = rows[-2] if len(rows) > 1 else None
    delta = latest["value"] - previous["value"] if latest and previous else None
    return {"success": True, "grain": args.grain, "periods": rows[-100:], "latest": latest,
            "previous": previous, "delta": delta, "rows_analyzed": handle.row_count(),
            "total_rows": handle.row_count(), "sampled": False}


async def _compare_segments(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, SegmentComparisonInput)
    metric = MetricInput(column=args.value_column, aggregation=args.aggregation,
                         dimensions=[args.segment_column], limit=args.limit)
    return await _compute_metrics(metric, context)


async def _assess_data_quality(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, ColumnsInput)
    handle = _dataset(context)
    columns = args.columns or handle.column_names()
    available = set(handle.column_names())
    results = []
    for name in columns:
        if name not in available:
            raise AgentToolError(f"UNKNOWN_DATASET_COLUMN:{name}")
        column = _quote_ident(name)
        row = handle.execute_select(
            f"SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE {column} IS NULL) AS null_count, "
            f"COUNT({column}) AS non_null_count, COUNT(DISTINCT {column}) AS distinct_count FROM df",
            max_rows=2,
        ).iloc[0]
        non_null = int(row["non_null_count"])
        results.append({
            "column": name,
            "null_count": int(row["null_count"]),
            "null_rate": float(row["null_count"] / max(1, row["total"])),
            "distinct_count": int(row["distinct_count"]),
            "duplicate_rate": float(1 - row["distinct_count"] / max(1, non_null)),
        })
    return {"success": True, "columns": results, "rows_analyzed": handle.row_count(),
            "total_rows": handle.row_count(), "sampled": False}


async def _explain_evidence(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, ExplainEvidenceInput)
    findings = list((context.analytics_results or {}).get("structured_findings") or [])
    if args.finding_ids:
        wanted = set(args.finding_ids)
        findings = [item for item in findings if item.get("id") in wanted]
    return {"success": True, "findings": findings[:50], "count": len(findings),
            "policy": "Only server-computed findings may support numeric claims."}


async def _distribution(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, DistributionInput)
    handle = _dataset(context)
    if args.column not in handle.column_names():
        raise AgentToolError(f"UNKNOWN_DATASET_COLUMN:{args.column}")
    column = _quote_ident(args.column)
    row = handle.execute_select(
        f"SELECT COUNT(TRY_CAST({column} AS DOUBLE)) AS count, "
        f"AVG(TRY_CAST({column} AS DOUBLE)) AS mean, STDDEV_SAMP(TRY_CAST({column} AS DOUBLE)) AS stddev, "
        f"SKEWNESS(TRY_CAST({column} AS DOUBLE)) AS skew, "
        f"QUANTILE_CONT(TRY_CAST({column} AS DOUBLE), [0, .05, .25, .5, .75, .95, 1]) AS quantiles FROM df",
        max_rows=2,
    ).iloc[0]
    if not int(row["count"]):
        raise AgentToolError("NUMERIC_COLUMN_REQUIRED")
    probabilities = (0, .05, .25, .5, .75, .95, 1)
    return {"success": True, "column": args.column, "count": int(row["count"]),
            "mean": float(row["mean"]), "stddev": float(row["stddev"]),
            "quantiles": {str(key): float(value) for key, value in zip(probabilities, row["quantiles"])},
            "skew": None if pd.isna(row["skew"]) else float(row["skew"]),
            "rows_analyzed": handle.row_count(), "sampled": False}


async def _relationship(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, RelationshipInput)
    handle = _dataset(context)
    if args.x_column not in handle.column_names() or args.y_column not in handle.column_names():
        raise AgentToolError("UNKNOWN_DATASET_COLUMN")
    x, y = _quote_ident(args.x_column), _quote_ident(args.y_column)
    row = handle.execute_select(
        f"SELECT COUNT(*) FILTER (WHERE TRY_CAST({x} AS DOUBLE) IS NOT NULL AND TRY_CAST({y} AS DOUBLE) IS NOT NULL) AS n, "
        f"CORR(TRY_CAST({x} AS DOUBLE), TRY_CAST({y} AS DOUBLE)) AS correlation FROM df",
        max_rows=2,
    ).iloc[0]
    if int(row["n"]) < 3:
        raise AgentToolError("RELATIONSHIP_REQUIRES_THREE_COMPLETE_ROWS")
    return {"success": True, "method": "pearson", "x_column": args.x_column,
            "y_column": args.y_column, "correlation": float(row["correlation"]), "n": int(row["n"]),
            "caveat": "Association is not evidence of causation."}


async def _anomalies(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, DistributionInput)
    handle = _dataset(context)
    if args.column not in handle.column_names():
        raise AgentToolError(f"UNKNOWN_DATASET_COLUMN:{args.column}")
    column = _quote_ident(args.column)
    frame = handle.execute_select(
        "WITH values AS (SELECT TRY_CAST(" + column + " AS DOUBLE) AS value FROM df), "
        "stats AS (SELECT AVG(value) AS mean, STDDEV_SAMP(value) AS stddev FROM values), "
        "scored AS (SELECT value, (value - mean) / NULLIF(stddev, 0) AS z_score FROM values, stats) "
        "SELECT value, z_score, COUNT(*) OVER () AS anomaly_count FROM scored "
        "WHERE ABS(z_score) >= 3 ORDER BY ABS(z_score) DESC LIMIT 100",
        max_rows=100,
    )
    rows = frame[["value", "z_score"]].replace({np.nan: None}).to_dict(orient="records") if not frame.empty else []
    anomaly_count = int(frame.iloc[0]["anomaly_count"]) if not frame.empty else 0
    return {"success": True, "method": "z_score_3", "column": args.column,
            "anomaly_count": anomaly_count, "anomalies": rows,
            "rows_analyzed": handle.row_count(), "sampled": False}


async def _forecast(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, ForecastInput)
    result = forecast_metric(_dataset(context), {"date": args.date_column, "sales": args.value_column}, horizon=args.horizon)
    return result or {"eligible": False, "reason": "Required date/value columns are unavailable."}


async def _scenario(args: BaseModel, _context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, ScenarioInput)
    result = parse_and_run_scenario(args.question, args.baseline_values)
    return result or {"eligible": False, "reason": "No bounded percentage scenario could be parsed."}


async def _cohort(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, CohortInput)
    _, frame = _sample(context)
    entities = _column(frame, args.entity_column).astype(str)
    dates = pd.to_datetime(_column(frame, args.date_column), errors="coerce", utc=True).dt.tz_localize(None)
    work = pd.DataFrame({"entity": entities, "date": dates}).dropna()
    work["cohort"] = work.groupby("entity")["date"].transform("min").dt.to_period("M")
    work["period"] = work["date"].dt.to_period("M")
    work["age"] = (work["period"].astype(int) - work["cohort"].astype(int)).clip(lower=0)
    matrix = work.groupby(["cohort", "age"])["entity"].nunique().unstack(fill_value=0)
    base = matrix.get(0, pd.Series(index=matrix.index, dtype=float)).replace(0, np.nan)
    retention = matrix.div(base, axis=0).fillna(0)
    rows = [{"cohort": str(cohort), **{str(int(age)): float(value) for age, value in row.items()}}
            for cohort, row in retention.head(36).iterrows()]
    return {"success": True, "method": "monthly_retention", "cohorts": rows}


async def _causal_eligibility(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, CausalInput)
    contract = {**(context.data_contract or {}), **args.design}
    return build_causal_eligibility(_dataset(context), data_contract=contract,
                                    analytics_results=context.analytics_results)


async def _causal_effect(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    eligibility = await _causal_eligibility(args, context)
    return run_causal_analyses(_dataset(context), eligibility)


async def _list_data_sources(_args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    return {"success": True, "sources": [{"source_id": key, "rows": value.row_count(),
                                             "columns": value.column_names()}
                                            for key, value in context.data_sources.items()]}


async def _plan_join(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, JoinPlanInput)
    try:
        left, right = context.data_sources[args.left_source], context.data_sources[args.right_source]
    except KeyError as exc:
        raise AgentToolError("JOIN_SOURCE_NOT_AVAILABLE") from exc
    left_frame = left.to_pandas(limit=min(left.row_count(), 200_000))
    right_frame = right.to_pandas(limit=min(right.row_count(), 200_000))
    _column(left_frame, args.left_key); _column(right_frame, args.right_key)
    assessment = assess_join_cardinality(left_frame, right_frame, args.left_key, args.right_key)
    left_keys = set(left_frame[args.left_key].dropna())
    right_keys = set(right_frame[args.right_key].dropna())
    assessment.update({
        "left_source": args.left_source, "right_source": args.right_source,
        "left_key": args.left_key, "right_key": args.right_key, "how": args.how,
        "match_rate": len(left_keys & right_keys) / max(1, len(left_keys)),
        "preview_only": True,
    })
    return assessment


async def _execute_join(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    assert isinstance(args, JoinPlanInput)
    plan = await _plan_join(args, context)
    if not plan.get("safe"):
        raise AgentToolError("JOIN_PLAN_NOT_SAFE")
    left = context.data_sources[args.left_source]
    right = context.data_sources[args.right_source]
    if left.row_count() > 200_000 or right.row_count() > 200_000:
        raise AgentToolError("JOIN_REQUIRES_VERSIONED_DUCKDB_ETL")
    joined = left.to_pandas().merge(
        right.to_pandas(), how=args.how,
        left_on=args.left_key, right_on=args.right_key,
        suffixes=("_left", "_right"), validate={
            "one_to_one": "one_to_one", "one_to_many": "one_to_many",
            "many_to_one": "many_to_one",
        }.get(str(plan.get("cardinality"))),
    )
    context.handle = DatasetHandle.from_dataframe(joined)
    plan.update({"confirmed": True, "persisted": False,
                 "joined_rows": len(joined), "joined_columns": list(joined.columns),
                 "message": "Joined in the current analysis session. Persist only through versioned ETL."})
    return plan


async def _validate_dax(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    from app.services.dax_engine import validate_dax_expression

    assert isinstance(args, DaxExpressionInput)
    return validate_dax_expression(
        args.expression, columns=_dataset(context).column_names(), mode="measure"
    )


def _preview_dax_handler(mode: Literal["measure", "calculated_column"]) -> ToolHandler:
    async def execute(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
        from app.services.dax_engine import validate_dax_expression

        assert isinstance(args, DaxDefinitionInput)
        handle = _dataset(context)
        validation = validate_dax_expression(
            args.expression, columns=handle.column_names(), mode=mode
        )
        if not validation["executable"]:
            raise AgentToolError(str(validation["execution_error"]))
        expression = validation["compiled_expression"]
        if mode == "measure":
            frame = handle.execute_select(f'SELECT {expression} AS "value" FROM df', max_rows=2)
            preview: Dict[str, Any] = {"value": None if frame.empty else frame.iloc[0, 0]}
        else:
            frame = handle.execute_select(f'SELECT {expression} AS "value" FROM df', max_rows=100)
            preview = {"rows": frame.replace({np.nan: None}).to_dict(orient="records"),
                       "null_count": int(frame.iloc[:, 0].isna().sum()) if not frame.empty else 0}
        approval_material = ":".join((
            validation["formula_hash"], args.dataset_key, args.name, mode,
        ))
        return {
            "success": True, "action": "preview_dax_definition",
            "dataset_key": args.dataset_key, "name": args.name,
            "label": args.label, "expression": args.expression, "mode": mode,
            "validation": validation, "preview": preview,
            "approved_action_id": "daxapprove_" + hashlib.sha256(
                approval_material.encode("utf-8")
            ).hexdigest(),
            "requires_confirmation": True,
        }
    return execute


async def _save_dax_measure(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    from app.services.dax_engine import validate_dax_expression
    from app.services.semantic_metrics import upsert_custom_metric

    assert isinstance(args, DaxDefinitionInput)
    handle = _dataset(context)
    validation = validate_dax_expression(args.expression, columns=handle.column_names(), mode="measure")
    if not validation["executable"]:
        raise AgentToolError(str(validation["execution_error"]))
    definition = {
        "key": args.name.strip().lower().replace(" ", "_"), "label": args.label or args.name,
        "aggregation": "dax_subset", "language": "dax_subset_v1",
        "expression": args.expression, "normalized_ast": validation["normalized_ast"],
        "dependencies": validation["dependencies"], "formula_hash": validation["formula_hash"],
        "output_type": validation["output_type"], "version": validation["version"],
    }
    saved = await asyncio.to_thread(
        upsert_custom_metric, context.user_id, args.dataset_key, definition
    )
    return {"success": True, "definition": saved}


async def _publish_calculated_column(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    from app.core.supabase import get_supabase_client
    from app.services.dax_engine import validate_dax_expression
    from app.services.etl_execution import execute_etl_recipe
    from app.services.etl_pipeline import normalize_recipe, recipe_hash

    assert isinstance(args, DaxDefinitionInput)
    validation = validate_dax_expression(
        args.expression, columns=_dataset(context).column_names(), mode="calculated_column"
    )
    if not validation["executable"]:
        raise AgentToolError(str(validation["execution_error"]))
    recipe = normalize_recipe({"apply": True, "transformations": [{
        "type": "dax_calculated", "name": args.name, "expression": args.expression,
        "normalized_ast": validation["normalized_ast"],
        "formula_hash": validation["formula_hash"], "confirmed": True,
    }]})
    db = get_supabase_client()
    payload = {"user_id": context.user_id, "dataset_key": args.dataset_key,
               "name": f"Calculated column: {args.name}"[:120], "version": 1,
               "recipe": recipe, "recipe_hash": recipe_hash(recipe), "is_active": True}
    previous = (db.table("etl_recipes").select("version").eq("user_id", context.user_id)
                .eq("dataset_key", args.dataset_key).order("version", desc=True).limit(1).execute())
    payload["version"] = int(previous.data[0]["version"]) + 1 if previous.data else 1
    inserted = db.table("etl_recipes").insert(payload).execute()
    recipe_row = (inserted.data or [payload])[0]
    if not recipe_row.get("id"):
        raise AgentToolError("ETL_RECIPE_PERSISTENCE_FAILED")
    result = await asyncio.to_thread(
        execute_etl_recipe, context.user_id, recipe_row["id"],
        output_name=f"{args.name}_dataset",
    )
    return {"success": True, "recipe": recipe_row, "dataset_version": result}


async def _validate_python(args: BaseModel, _context: AgentToolContext) -> Dict[str, Any]:
    from app.services.python_sandbox import validate_python_code

    assert isinstance(args, PythonCodeInput)
    return validate_python_code(args.code, args.packages)


async def _propose_python(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    from app.services.python_sandbox import propose_python_analysis

    assert isinstance(args, PythonProposalInput)
    return await asyncio.to_thread(
        propose_python_analysis,
        user_id=context.user_id, conversation_id=context.conversation_id,
        dataset_key=args.dataset_key, dataset_version_hash=args.dataset_version_hash,
        code=args.code, packages=args.packages, expected_outputs=args.expected_outputs,
    )


async def _run_python(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    from app.services.python_sandbox import confirm_python_analysis

    assert isinstance(args, PythonJobInput)
    if not args.approval_id:
        raise ToolPermissionError("PYTHON_APPROVAL_ID_REQUIRED")
    return await asyncio.to_thread(
        confirm_python_analysis, context.user_id, args.job_id, args.approval_id
    )


async def _cancel_python(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    from app.services.python_sandbox import cancel_python_analysis

    assert isinstance(args, PythonJobInput)
    return await cancel_python_analysis(context.user_id, args.job_id)


def _chart_schema(context: AgentToolContext) -> list[dict[str, Any]]:
    from app.services.chart_builder import schema_from_handle

    return schema_from_handle(_dataset(context))


async def _list_chart_fields(_args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    from app.services.chart_builder import list_chart_fields

    fields = list_chart_fields(_chart_schema(context))
    return {"success": True, "engine": "duckdb", **fields}


async def _add_chart(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    from app.services.chart_builder import ChartBuilderError, add_chart, inspect_chart

    assert isinstance(args, AddChartInput)
    schema = _chart_schema(context)
    try:
        widget = add_chart(schema, chart_type=args.chart_type, title=args.title)
    except ChartBuilderError as exc:
        raise AgentToolError(str(exc)) from exc
    return {
        "success": True,
        "widget": widget,
        "inspect": inspect_chart(widget, schema, row_count=_dataset(context).row_count()),
    }


async def _rename_chart(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    from app.services.chart_builder import inspect_chart

    assert isinstance(args, RenameChartInput)
    widget = {**args.widget, "title": args.title.strip()[:160]}
    schema = _chart_schema(context)
    return {
        "success": True,
        "widget": widget,
        "inspect": inspect_chart(widget, schema, row_count=_dataset(context).row_count()),
    }


async def _bind_chart_field(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    from app.services.chart_builder import ChartBuilderError, bind_chart_field, inspect_chart

    assert isinstance(args, BindChartFieldInput)
    schema = _chart_schema(context)
    try:
        widget = bind_chart_field(
            args.widget,
            args.well,
            args.column,
            schema,
            aggregation=args.aggregation,
        )
    except ChartBuilderError as exc:
        raise AgentToolError(str(exc)) from exc
    return {
        "success": True,
        "widget": widget,
        "inspect": inspect_chart(widget, schema, row_count=_dataset(context).row_count()),
    }


async def _inspect_chart(args: BaseModel, context: AgentToolContext) -> Dict[str, Any]:
    from app.services.chart_builder import inspect_chart

    assert isinstance(args, ChartWidgetInput)
    schema = _chart_schema(context)
    payload = inspect_chart(
        args.widget,
        schema,
        row_count=_dataset(context).row_count(),
    )
    payload["success"] = True
    return payload


def _definitions() -> Iterable[AgentToolDefinition]:
    yield AgentToolDefinition(
        tool_id="query_data",
        name="Query Data",
        description="Run a governed analytical question over the ready dataset.",
        category="analytics",
        input_model=DatasetQueryInput,
        handler=_query_data,
        authority="question_analytics.run_question_aware_analytics",
        timeout_seconds=90,
        max_retries=0,
        cost_units=2,
        requires_dataset=True,
    )
    core_tools: tuple[tuple[str, str, str, Type[BaseModel], ToolHandler], ...] = (
        ("inspect_dataset", "Inspect Dataset", "Inspect schema, grain, quality metadata, and a bounded sample.", DatasetInspectInput, _inspect_dataset),
        ("compute_metrics", "Compute Metrics", "Compute a governed aggregation and optional dimensional breakdown.", MetricInput, _compute_metrics),
        ("compare_periods", "Compare Periods", "Compare a metric over deterministic calendar periods.", PeriodComparisonInput, _compare_periods),
        ("compare_segments", "Compare Segments", "Compare a metric across one governed segment.", SegmentComparisonInput, _compare_segments),
        ("assess_data_quality", "Assess Data Quality", "Measure null, distinct, and duplicate rates.", ColumnsInput, _assess_data_quality),
        ("explain_evidence", "Explain Evidence", "Return verifier-compatible evidence and provenance.", ExplainEvidenceInput, _explain_evidence),
        ("list_chart_fields", "List Chart Fields", "List Axis/Values fields the core charts can bind.", EmptyInput, _list_chart_fields),
    )
    for tool_id, name, description, input_model, handler in core_tools:
        yield AgentToolDefinition(
            tool_id=tool_id, name=name, description=description, category="analytics",
            input_model=input_model, handler=handler,
            authority=f"agent_tool_registry.{handler.__name__}", requires_dataset=True,
            output_schema={"type": "object", "required": ["success"]},
        )
    yield AgentToolDefinition(
        tool_id="add_chart",
        name="Add Chart",
        description="Create a core chart spec (bar, line, area, pie, pareto) from dataset fields. Does not persist a report.",
        category="analytics",
        input_model=AddChartInput,
        handler=_add_chart,
        authority="chart_builder.add_chart",
        requires_dataset=True,
    )
    yield AgentToolDefinition(
        tool_id="rename_chart",
        name="Rename Chart",
        description="Set a human-readable title on a chart spec without changing its fields.",
        category="analytics",
        input_model=RenameChartInput,
        handler=_rename_chart,
        authority="chart_builder.inspect_chart",
        requires_dataset=True,
    )
    yield AgentToolDefinition(
        tool_id="bind_chart_field",
        name="Bind Chart Field",
        description="Bind a dataset column to chart X (category) or Y (value). DuckDB owns aggregation. Does not rename the chart.",
        category="analytics",
        input_model=BindChartFieldInput,
        handler=_bind_chart_field,
        authority="chart_builder.bind_chart_field",
        requires_dataset=True,
    )
    yield AgentToolDefinition(
        tool_id="inspect_chart",
        name="Inspect Chart",
        description="Return the fields, formula, and engine for a chart so a person can verify it.",
        category="analytics",
        input_model=ChartWidgetInput,
        handler=_inspect_chart,
        authority="chart_builder.inspect_chart",
        requires_dataset=True,
    )
    advanced_tools: tuple[tuple[str, str, str, Type[BaseModel], ToolHandler, tuple[str, ...]], ...] = (
        ("analyze_distribution", "Analyze Distribution", "Compute bounded descriptive distribution statistics.", DistributionInput, _distribution, ("free", "plus", "pro", "premium")),
        ("test_relationship", "Test Relationship", "Measure a numeric relationship with explicit caveats.", RelationshipInput, _relationship, ("free", "plus", "pro", "premium")),
        ("detect_anomalies", "Detect Anomalies", "Detect extreme numeric observations with a deterministic method.", DistributionInput, _anomalies, ("free", "plus", "pro", "premium")),
        ("forecast_series", "Forecast Series", "Produce a bounded forecast with uncertainty metadata.", ForecastInput, _forecast, ("free", "plus", "pro", "premium")),
        ("run_scenario", "Run Scenario", "Run a bounded percentage what-if scenario.", ScenarioInput, _scenario, ("free", "plus", "pro", "premium")),
        ("analyze_cohort_funnel", "Analyze Cohort", "Compute monthly cohort retention.", CohortInput, _cohort, ("free", "plus", "pro", "premium")),
        ("evaluate_causal_design", "Evaluate Causal Design", "Check causal-design eligibility before estimation.", CausalInput, _causal_eligibility, ("pro", "premium")),
        ("estimate_causal_effect", "Estimate Causal Effect", "Run only estimators whose design gates pass.", CausalInput, _causal_effect, ("pro", "premium")),
    )
    for tool_id, name, description, input_model, handler, tiers in advanced_tools:
        yield AgentToolDefinition(
            tool_id=tool_id, name=name, description=description, category="analytics",
            input_model=input_model, handler=handler,
            authority=f"agent_tool_registry.{handler.__name__}", requires_dataset=True,
            allowed_tiers=tiers, cost_units=2,
        )
    yield AgentToolDefinition(
        tool_id="list_data_sources", name="List Data Sources",
        description="List data sources already authorized for this analysis context.",
        category="analytics", input_model=EmptyInput, handler=_list_data_sources,
        authority="agent_context.data_sources", allowed_tiers=("pro", "premium"),
    )
    yield AgentToolDefinition(
        tool_id="plan_dataset_join", name="Plan Dataset Join",
        description="Preview join keys, cardinality, match rate, and row multiplication.",
        category="analytics", input_model=JoinPlanInput, handler=_plan_join,
        authority="analytical_extensions.assess_join_cardinality",
        allowed_tiers=("pro", "premium"), cost_units=2,
    )
    yield AgentToolDefinition(
        tool_id="execute_dataset_join", name="Execute Dataset Join",
        description="Confirm a safe governed join; persistence remains in versioned ETL.",
        category="analytics", input_model=JoinPlanInput, handler=_execute_join,
        authority="versioned_etl.governed_join", side_effect="write",
        allowed_tiers=("pro", "premium"), cost_units=3,
        requires_confirmation=True,
    )
    dax_tools: tuple[AgentToolDefinition, ...] = (
        AgentToolDefinition(
            tool_id="validate_dax_expression", name="Validate DAX Expression",
            description="Parse a documented DAX subset expression into a typed AST.",
            category="analytics", input_model=DaxExpressionInput, handler=_validate_dax,
            authority="dax_engine.validate_dax_expression", requires_dataset=True,
            allowed_tiers=("pro", "premium"),
        ),
        AgentToolDefinition(
            tool_id="preview_dax_measure", name="Preview DAX Measure",
            description="Compile and preview a DAX subset measure without persistence.",
            category="analytics", input_model=DaxDefinitionInput,
            handler=_preview_dax_handler("measure"), authority="dax_engine.compile_dax_expression",
            requires_dataset=True, allowed_tiers=("pro", "premium"), cost_units=2,
        ),
        AgentToolDefinition(
            tool_id="save_dax_measure", name="Save DAX Measure",
            description="Persist an approved DAX subset measure in semantic definitions.",
            category="analytics", input_model=DaxDefinitionInput, handler=_save_dax_measure,
            authority="semantic_metrics.upsert_custom_metric", side_effect="write",
            requires_dataset=True, allowed_tiers=("pro", "premium"), cost_units=2,
            requires_confirmation=True,
        ),
        AgentToolDefinition(
            tool_id="preview_calculated_column", name="Preview Calculated Column",
            description="Preview values and nulls for a DAX subset calculated column.",
            category="analytics", input_model=DaxDefinitionInput,
            handler=_preview_dax_handler("calculated_column"),
            authority="dax_engine.compile_dax_expression", requires_dataset=True,
            allowed_tiers=("pro", "premium"), cost_units=2,
        ),
        AgentToolDefinition(
            tool_id="publish_calculated_column", name="Publish Calculated Column",
            description="Publish an approved calculated column as a versioned ETL output.",
            category="analytics", input_model=DaxDefinitionInput,
            handler=_publish_calculated_column, authority="etl_execution.execute_etl_recipe",
            side_effect="write", requires_dataset=True, allowed_tiers=("pro", "premium"),
            cost_units=3, requires_confirmation=True,
        ),
    )
    yield from dax_tools
    yield AgentToolDefinition(
        tool_id="validate_python_code", name="Validate Python Code",
        description="Statically validate bounded analysis code and package manifest.",
        category="analytics", input_model=PythonCodeInput, handler=_validate_python,
        authority="python_sandbox.validate_python_code", allowed_tiers=("pro", "premium"),
        execution_environment="server",
    )
    yield AgentToolDefinition(
        tool_id="propose_python_analysis", name="Propose Python Analysis",
        description="Store code, packages, inputs, outputs, and limits for user review.",
        category="analytics", input_model=PythonProposalInput, handler=_propose_python,
        authority="python_sandbox.propose_python_analysis", side_effect="write",
        allowed_tiers=("pro", "premium"), cost_units=2,
    )
    yield AgentToolDefinition(
        tool_id="run_python_analysis", name="Run Python Analysis",
        description="Queue an exact hash-approved job for an external isolated sandbox.",
        category="analytics", input_model=PythonJobInput, handler=_run_python,
        authority="python_sandbox.confirm_python_analysis", side_effect="write",
        allowed_tiers=("pro", "premium"), cost_units=4,
        requires_confirmation=True, execution_environment="external_sandbox",
    )
    yield AgentToolDefinition(
        tool_id="cancel_python_analysis", name="Cancel Python Analysis",
        description="Cancel a queued or running Python analysis job.",
        category="analytics", input_model=PythonJobInput, handler=_cancel_python,
        authority="python_sandbox.cancel_python_analysis", side_effect="write",
        allowed_tiers=("pro", "premium"), execution_environment="external_sandbox",
    )
    yield AgentToolDefinition(
        tool_id="safe_calculator",
        name="Safe Calculator",
        description=(
            "Evaluate a bounded arithmetic expression only (e.g. 1200+300, 20% of 50). "
            "Do NOT use for weather, FX rates, news, dates, or anything needing live data."
        ),
        category="utility",
        input_model=CalculatorInput,
        handler=_calculator,
        authority="calculator.calculate_from_question",
        timeout_seconds=3,
    )
    yield AgentToolDefinition(
        tool_id="server_clock",
        name="Server Clock",
        description=(
            "Return the authoritative current date and wall-clock time from the server. "
            "Use only when the user asks what time or date it is now. "
            "Do NOT use for weather forecasts, exchange rates, or dataset analysis."
        ),
        category="utility",
        input_model=ServerClockInput,
        handler=_server_clock,
        authority="server_clock.build_server_clock_tool_result",
        timeout_seconds=2,
        cost_units=0,
    )
    yield AgentToolDefinition(
        tool_id="web_search",
        name="Web Search",
        description=(
            "Fetch current public-web evidence (weather, FX, prices, news, benchmarks). "
            "Use for live external facts. Do NOT use for pure arithmetic or asking the current clock time."
        ),
        category="external_context",
        input_model=WebSearchInput,
        handler=_web_search,
        authority="web_search.run_multi_web_search",
        timeout_seconds=30,
        max_retries=1,
        cost_units=2,
        allowed_tiers=("plus", "pro"),
    )
    for step_type in ("inspect", "prepare", "map", "validate", "clean", "finalize"):
        yield AgentToolDefinition(
            tool_id=step_type,
            name=f"Data Setup: {step_type.title()}",
            description=f"Execute the governed {step_type} workflow step.",
            category="data_setup",
            input_model=SetupStepInput,
            handler=_setup_handler(step_type),
            authority="workflow_engine.execute_step",
            side_effect="write",
            timeout_seconds=120,
            cost_units=2,
        )


AGENT_TOOL_REGISTRY: Dict[str, AgentToolDefinition] = {
    definition.tool_id: definition for definition in _definitions()
}


def get_agent_tool(tool_id: str) -> AgentToolDefinition:
    definition = AGENT_TOOL_REGISTRY.get(str(tool_id or "").strip())
    if definition is None:
        raise UnknownAgentToolError(f"UNKNOWN_TOOL: {tool_id}")
    return definition


def list_agent_tools(*, category: Optional[ToolCategory] = None) -> List[Dict[str, Any]]:
    definitions = AGENT_TOOL_REGISTRY.values()
    if category:
        definitions = (item for item in definitions if item.category == category)
    return [item.public_dict() for item in definitions]


class AgentToolDispatcher:
    """Validate, authorize, budget, retry, time out, cache, and audit calls."""

    def __init__(self) -> None:
        self._cache: Dict[str, AgentToolDispatchResult] = {}

    async def execute(
        self,
        call: AgentToolCall | Dict[str, Any],
        *,
        context: AgentToolContext,
        budget: AgentToolBudget,
    ) -> AgentToolDispatchResult:
        request = call if isinstance(call, AgentToolCall) else AgentToolCall.model_validate(call)
        definition = get_agent_tool(request.tool_id)
        if context.user_tier not in definition.allowed_tiers:
            raise ToolPermissionError(f"TOOL_NOT_ALLOWED_FOR_TIER: {request.tool_id}")
        if definition.requires_dataset and context.handle is None:
            raise ToolPermissionError(f"DATASET_REQUIRED: {request.tool_id}")
        if (
            definition.category == "analytics"
            and definition.requires_dataset
            and context.data_contract
            and request.tool_id not in {"inspect_dataset", "assess_data_quality", "list_chart_fields"}
        ):
            mapping_gate = evaluate_semantic_mapping_gate(
                mapping=context.column_mapping,
                data_contract=context.data_contract,
                columns=context.handle.column_names() if context.handle is not None else [],
                require_confirmation=True,
            )
            if not mapping_gate["ready"]:
                raise ToolPermissionError("SEMANTIC_MAPPING_REQUIRED")
        if definition.requires_confirmation:
            approved = request.approved_action_id
            if not approved or approved not in context.approved_action_ids:
                raise ToolPermissionError(
                    f"TOOL_CONFIRMATION_REQUIRED: {request.tool_id}"
                )

        try:
            validated = definition.input_model.model_validate(request.arguments)
        except ValidationError as exc:
            raise AgentToolError(f"INVALID_TOOL_INPUT: {request.tool_id}") from exc

        safe_input = validated.model_dump(mode="json")
        input_hash = _stable_hash({"tool_id": request.tool_id, "input": safe_input})
        idempotency_key = request.idempotency_key or input_hash
        cache_key = f"{context.user_id}:{request.tool_id}:{idempotency_key}"
        if definition.idempotent and cache_key in self._cache:
            cached = self._cache[cache_key]
            record = cached.record.model_copy(update={
                "status": "cached",
                "attempts": 0,
                "duration_ms": 0,
                "cost_units": 0,
            })
            return AgentToolDispatchResult(record=record, output=cached.output)

        budget.reserve(definition)
        started = datetime.now(timezone.utc)
        started_clock = time.perf_counter()
        attempts = 0
        output: Optional[Dict[str, Any]] = None
        status: ToolCallStatus = "failed"
        error_code: Optional[str] = None
        error: Optional[str] = None

        while attempts <= definition.max_retries:
            attempts += 1
            try:
                maybe_result = definition.handler(validated, context)
                if inspect.isawaitable(maybe_result):
                    output = await asyncio.wait_for(
                        maybe_result,
                        timeout=definition.timeout_seconds,
                    )
                else:
                    output = maybe_result
                if not isinstance(output, dict):
                    raise AgentToolError("INVALID_TOOL_OUTPUT")
                status = "completed"
                break
            except asyncio.CancelledError:
                status = "cancelled"
                error_code = "TOOL_CANCELLED"
                error = "Tool execution was cancelled."
                raise
            except asyncio.TimeoutError as exc:
                status = "timed_out"
                error_code = "TOOL_TIMEOUT"
                error = f"Tool exceeded {definition.timeout_seconds:g}s timeout."
                if attempts > definition.max_retries:
                    break
                await asyncio.sleep(0)
            except definition.retryable_exceptions as exc:
                status = "failed"
                error_code = type(exc).__name__
                error = str(exc)[:240]
                if attempts > definition.max_retries:
                    break
                await asyncio.sleep(0)
            except Exception as exc:
                status = "failed"
                error_code = type(exc).__name__
                error = str(exc)[:240]
                break

        completed = datetime.now(timezone.utc)
        record = AgentToolCallRecord(
            call_id=f"call_{input_hash[:16]}",
            tool_id=request.tool_id,
            status=status,
            reason=request.reason,
            attempts=attempts,
            duration_ms=int((time.perf_counter() - started_clock) * 1000),
            cost_units=definition.cost_units,
            idempotency_key=idempotency_key,
            input_hash=input_hash,
            output_summary=_bounded_output_summary(output),
            error_code=error_code,
            error=error,
            started_at=started.isoformat(),
            completed_at=completed.isoformat(),
        )
        dispatched = AgentToolDispatchResult(record=record, output=output)
        if status == "completed" and definition.idempotent:
            self._cache[cache_key] = dispatched
        return dispatched
