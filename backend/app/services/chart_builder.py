"""Shared chart field-well contract for people and the agent.

The model may choose chart type and bind columns to Axis/Values. DuckDB still
owns aggregation. Core visuals only: bar, line, area, pie, pareto.
"""
from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from app.services.dataset_engine import DatasetHandle

CORE_CHART_TYPES = ("bar", "line", "area", "pie", "pareto")
CHART_WELLS = ("axis", "values")
COUNT_FIELD = "*"
ALLOWED_AGGREGATIONS = ("sum", "average", "count")
WELL_ALIASES = {
    "x": "axis",
    "xaxis": "axis",
    "x-axis": "axis",
    "axis": "axis",
    "category": "axis",
    "y": "values",
    "yaxis": "values",
    "y-axis": "values",
    "values": "values",
    "value": "values",
    "measure": "values",
}


def normalize_chart_well(well: str | None) -> str | None:
    return WELL_ALIASES.get(str(well or "").strip().lower())


class ChartBuilderError(ValueError):
    pass


def schema_from_handle(handle: DatasetHandle, sample_rows: int = 4_000) -> list[dict[str, Any]]:
    sample = handle.to_pandas(limit=min(handle.row_count(), sample_rows))
    schema: list[dict[str, Any]] = []
    for name in handle.column_names():
        series = sample[name] if name in sample.columns else pd.Series(dtype="object")
        kind = "text"
        if pd.api.types.is_numeric_dtype(series):
            kind = "number"
        elif pd.api.types.is_datetime64_any_dtype(series):
            kind = "date"
        schema.append({"name": str(name), "kind": kind})
    return schema


def list_chart_fields(schema: list[Mapping[str, Any]]) -> dict[str, Any]:
    dimensions = [item for item in schema if item.get("kind") in {"text", "date"}]
    measures = [item for item in schema if item.get("kind") == "number"]
    return {
        "wells": ["x", "y"],
        "well_aliases": {"x": "axis", "y": "values"},
        "chart_types": list(CORE_CHART_TYPES),
        "dimensions": dimensions,
        "measures": measures,
        "count_field": COUNT_FIELD,
    }


def _column_meta(schema: list[Mapping[str, Any]], name: str) -> dict[str, Any] | None:
    return next((dict(item) for item in schema if str(item.get("name")) == str(name)), None)


def chart_formula(widget: Mapping[str, Any]) -> str:
    if str(widget.get("kind") or "chart") == "table":
        columns = ", ".join(str(column) for column in widget.get("columns") or [])
        return f"SELECT {columns}" if columns else "SELECT *"
    dimension = str(widget.get("dimension") or "—")
    if widget.get("aggregation") == "count" or not widget.get("measure"):
        return f"COUNT(*) GROUP BY {dimension}"
    function = "AVG" if widget.get("aggregation") == "average" else "SUM"
    return f"{function}({widget.get('measure')}) GROUP BY {dimension}"


def inspect_chart(
    widget: Mapping[str, Any],
    schema: list[Mapping[str, Any]] | None = None,
    *,
    row_count: int | None = None,
    filtered_row_count: int | None = None,
    point_count: int | None = None,
) -> dict[str, Any]:
    schema = list(schema or [])
    axis_meta = _column_meta(schema, str(widget.get("dimension") or ""))
    if widget.get("aggregation") == "count" or not widget.get("measure"):
        values = {"field": COUNT_FIELD, "kind": "count", "aggregation": "count"}
    else:
        measure_meta = _column_meta(schema, str(widget.get("measure")))
        values = {
            "field": widget.get("measure"),
            "kind": (measure_meta or {}).get("kind") or "number",
            "aggregation": widget.get("aggregation") or "sum",
        }
    source_columns = [
        column for column in (widget.get("dimension"), widget.get("measure")) if column
    ]
    return {
        "success": True,
        "widget_id": widget.get("id"),
        "kind": widget.get("kind") or "chart",
        "chart_type": widget.get("chart_type") or "bar",
        "title": widget.get("title") or "",
        "wells": {
            "axis": (
                {"field": widget.get("dimension"), "kind": (axis_meta or {}).get("kind") or "text"}
                if widget.get("dimension")
                else None
            ),
            "values": values,
            "x": (
                {"field": widget.get("dimension"), "kind": (axis_meta or {}).get("kind") or "text"}
                if widget.get("dimension")
                else None
            ),
            "y": values,
        },
        "formula": chart_formula(widget),
        "engine": "duckdb",
        "time_grain": widget.get("time_grain"),
        "limit": widget.get("limit") or 20,
        "source_columns": source_columns,
        "row_count": row_count,
        "filtered_row_count": filtered_row_count,
        "point_count": point_count,
    }


def add_chart(
    schema: list[Mapping[str, Any]],
    *,
    chart_type: str = "bar",
    title: str | None = None,
) -> dict[str, Any]:
    if chart_type not in CORE_CHART_TYPES:
        raise ChartBuilderError(f"UNSUPPORTED_CHART_TYPE:{chart_type}")
    fields = list_chart_fields(schema)
    dimension = (fields["dimensions"][0]["name"] if fields["dimensions"] else "")
    measure = (fields["measures"][0]["name"] if fields["measures"] else None)
    is_date = bool(fields["dimensions"] and fields["dimensions"][0].get("kind") == "date")
    widget = {
        "id": None,
        "kind": "chart",
        "chart_type": chart_type,
        "title": (title.strip()[:160] if title and title.strip() else (
            f"{measure} by {dimension}" if measure and dimension else f"Count by {dimension}"
        )),
        "dimension": dimension,
        "measure": measure,
        "aggregation": "sum" if measure else "count",
        "time_grain": "month" if is_date else None,
        "limit": 12 if chart_type == "pie" else 20,
        "span": 6,
        "cross_filter": not is_date,
        "purpose": "trend" if chart_type in {"line", "area"} or is_date else (
            "distribution" if chart_type == "pie" else "ranking"
        ),
    }
    return widget


def bind_chart_field(
    widget: Mapping[str, Any],
    well: str,
    column: str,
    schema: list[Mapping[str, Any]],
    *,
    aggregation: str | None = None,
) -> dict[str, Any]:
    current = dict(widget or {})
    if str(current.get("kind") or "chart") == "table":
        raise ChartBuilderError("NOT_A_CHART")
    resolved_well = normalize_chart_well(well)
    if resolved_well not in CHART_WELLS:
        raise ChartBuilderError(f"UNKNOWN_WELL:{well}")
    current["kind"] = "chart"
    if resolved_well == "axis":
        meta = _column_meta(schema, column)
        if not meta or meta.get("kind") not in {"text", "date"}:
            raise ChartBuilderError("AXIS_NEEDS_DIMENSION")
        is_date = meta["kind"] == "date"
        current["dimension"] = meta["name"]
        current["time_grain"] = current.get("time_grain") or "month" if is_date else None
        current["cross_filter"] = not is_date
        if is_date:
            current["purpose"] = "trend"
        elif current.get("purpose") == "trend":
            current["purpose"] = "ranking"
        return current
    if column == COUNT_FIELD:
        current["aggregation"] = "count"
        current["measure"] = None
        return current
    meta = _column_meta(schema, column)
    if not meta or meta.get("kind") != "number":
        raise ChartBuilderError("VALUES_NEEDS_MEASURE")
    next_aggregation = aggregation if aggregation in {"sum", "average"} else (
        "sum" if current.get("aggregation") == "count" else (current.get("aggregation") or "sum")
    )
    if next_aggregation not in ALLOWED_AGGREGATIONS:
        raise ChartBuilderError(f"UNKNOWN_AGGREGATION:{next_aggregation}")
    current["measure"] = meta["name"]
    current["aggregation"] = next_aggregation
    return current
