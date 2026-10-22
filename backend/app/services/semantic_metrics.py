"""Server-owned semantic metrics with deterministic SQL and reusable definitions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from app.services.dataset_engine import DatasetHandle
from app.core.supabase import get_supabase_client


def quote_identifier(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    aggregation: str
    role: Optional[str] = None
    numerator_role: Optional[str] = None
    denominator_role: Optional[str] = None
    unit: str = "native"
    description: str = ""
    version: int = 1
    language: str = "builtin"
    expression: str = ""
    formula_hash: str = ""
    dependencies: tuple[str, ...] = ()
    normalized_ast: Optional[Dict[str, Any]] = None
    output_type: str = "number"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


BUILTIN_METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition("revenue", "Revenue", "sum", role="sales", description="Sum of recognized revenue."),
    MetricDefinition("cost", "Cost", "sum", role="cost", description="Sum of recognized cost."),
    MetricDefinition("profit", "Profit", "difference", numerator_role="sales", denominator_role="cost", description="Revenue minus cost."),
    MetricDefinition("gross_margin", "Gross margin", "difference_ratio", numerator_role="sales", denominator_role="cost", unit="%", description="(Revenue - cost) / revenue."),
    MetricDefinition("units", "Units", "sum", role="quantity", unit="units", description="Sum of units or quantity."),
    MetricDefinition("orders", "Orders", "count_distinct", role="order_id", unit="orders", description="Distinct order count."),
    MetricDefinition("customers", "Customers", "count_distinct", role="customer_id", unit="customers", description="Distinct customer count."),
    MetricDefinition("average_order_value", "Average order value", "sum_per_distinct", numerator_role="sales", denominator_role="order_id", description="Revenue divided by distinct orders."),
    MetricDefinition("click_through_rate", "Click-through rate", "ratio", numerator_role="clicks", denominator_role="impressions", unit="%", description="Clicks divided by impressions."),
    MetricDefinition("defect_rate", "Defect rate", "ratio", numerator_role="defects", denominator_role="output", unit="%", description="Defects divided by total output."),
)

ALLOWED_AGGREGATIONS = {
    "sum",
    "count_distinct",
    "difference",
    "difference_ratio",
    "sum_per_distinct",
    "ratio",
    "dax_subset",
}


def validate_custom_metric(definition: Dict[str, Any]) -> Dict[str, Any]:
    key = str(definition.get("key") or "").strip().lower()
    aggregation = str(definition.get("aggregation") or "").strip().lower()
    if not key or not key.replace("_", "").isalnum():
        raise ValueError("Metric key must contain only letters, numbers, and underscores.")
    if aggregation not in ALLOWED_AGGREGATIONS:
        raise ValueError(f"Unsupported metric aggregation: {aggregation}")
    if aggregation == "dax_subset":
        from app.services.dax_engine import parse_dax_expression, validate_dax_expression

        expression = str(definition.get("expression") or "").strip()
        dependencies = [str(item) for item in (definition.get("dependencies") or [])[:100]]
        parsed = parse_dax_expression(expression)
        _ = parsed  # Parsing is mandatory even though execution recompiles against the dataset.
        validation = validate_dax_expression(expression, columns=dependencies, mode="measure")
        supplied_hash = str(definition.get("formula_hash") or "")
        if supplied_hash and supplied_hash != validation["formula_hash"]:
            raise ValueError("DAX formula hash does not match the normalized AST.")
        return {
            "key": key,
            "label": str(definition.get("label") or key).strip()[:120],
            "aggregation": "dax_subset",
            "language": "dax_subset_v1",
            "expression": expression,
            "normalized_ast": validation["normalized_ast"],
            "dependencies": dependencies,
            "formula_hash": validation["formula_hash"],
            "output_type": str(definition.get("output_type") or "number")[:40],
            "unit": str(definition.get("unit") or "native")[:32],
            "description": str(definition.get("description") or "")[:500],
            "version": max(1, int(definition.get("version") or 1)),
        }
    normalized = {
        "key": key,
        "label": str(definition.get("label") or key).strip()[:120],
        "aggregation": aggregation,
        "role": definition.get("role"),
        "numerator_role": definition.get("numerator_role"),
        "denominator_role": definition.get("denominator_role"),
        "unit": str(definition.get("unit") or "native")[:32],
        "description": str(definition.get("description") or "")[:500],
        "version": max(1, int(definition.get("version") or 1)),
    }
    required = {
        "sum": ["role"],
        "count_distinct": ["role"],
        "difference": ["numerator_role", "denominator_role"],
        "difference_ratio": ["numerator_role", "denominator_role"],
        "sum_per_distinct": ["numerator_role", "denominator_role"],
        "ratio": ["numerator_role", "denominator_role"],
    }[aggregation]
    if any(not normalized.get(field) for field in required):
        raise ValueError(f"{aggregation} requires: {', '.join(required)}")
    return normalized


def fetch_custom_metrics(user_id: str, dataset_key: Optional[str]) -> List[Dict[str, Any]]:
    if not user_id or not dataset_key:
        return []
    try:
        response = (
            get_supabase_client()
            .table("semantic_metric_definitions")
            .select("definition")
            .eq("user_id", user_id)
            .eq("dataset_key", dataset_key)
            .eq("is_active", True)
            .order("updated_at", desc=True)
            .execute()
        )
        return [
            row["definition"] for row in (response.data or [])
            if isinstance(row.get("definition"), dict)
        ]
    except Exception as exc:
        if "semantic_metric_definitions" not in str(exc):
            print(f"fetch_custom_metrics failed: {exc}")
        return []


def upsert_custom_metric(
    user_id: str,
    dataset_key: str,
    definition: Dict[str, Any],
) -> Dict[str, Any]:
    normalized = validate_custom_metric(definition)
    response = (
        get_supabase_client()
        .table("semantic_metric_definitions")
        .upsert(
            {
                "user_id": user_id,
                "dataset_key": dataset_key,
                "metric_key": normalized["key"],
                "definition": normalized,
                "is_active": True,
            },
            on_conflict="user_id,dataset_key,metric_key",
        )
        .execute()
    )
    return (response.data or [{}])[0] or normalized


def delete_custom_metric(user_id: str, dataset_key: str, metric_key: str) -> None:
    (
        get_supabase_client()
        .table("semantic_metric_definitions")
        .delete()
        .eq("user_id", user_id)
        .eq("dataset_key", dataset_key)
        .eq("metric_key", metric_key)
        .execute()
    )


def resolve_metric_definitions(
    roles: Dict[str, str],
    custom: Optional[Iterable[Dict[str, Any]]] = None,
) -> List[MetricDefinition]:
    definitions = list(BUILTIN_METRICS)
    for item in custom or []:
        try:
            definitions.append(
                MetricDefinition(
                    key=str(item["key"]),
                    label=str(item.get("label") or item["key"]),
                    aggregation=str(item["aggregation"]),
                    role=item.get("role"),
                    numerator_role=item.get("numerator_role"),
                    denominator_role=item.get("denominator_role"),
                    unit=str(item.get("unit") or "native"),
                    description=str(item.get("description") or ""),
                    version=int(item.get("version") or 1),
                    language=str(item.get("language") or "builtin"),
                    expression=str(item.get("expression") or ""),
                    formula_hash=str(item.get("formula_hash") or ""),
                    dependencies=tuple(str(value) for value in item.get("dependencies") or []),
                    normalized_ast=item.get("normalized_ast") if isinstance(item.get("normalized_ast"), dict) else None,
                    output_type=str(item.get("output_type") or "number"),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    eligible: List[MetricDefinition] = []
    for definition in definitions:
        required = [
            role for role in (
                definition.role,
                definition.numerator_role,
                definition.denominator_role,
            )
            if role
        ]
        if all(roles.get(role) for role in required):
            eligible.append(definition)
    unique: Dict[str, MetricDefinition] = {}
    for definition in eligible:
        unique[definition.key] = definition
    return list(unique.values())


def metric_sql(definition: MetricDefinition, roles: Dict[str, str]) -> tuple[str, str]:
    alias = quote_identifier(definition.key)
    if definition.aggregation == "sum":
        column = quote_identifier(roles[definition.role or ""])
        expression = f"SUM(TRY_CAST({column} AS DOUBLE))"
        return f"SELECT {expression} AS {alias} FROM df", expression
    if definition.aggregation == "count_distinct":
        column = quote_identifier(roles[definition.role or ""])
        expression = f"COUNT(DISTINCT {column})"
        return f"SELECT {expression} AS {alias} FROM df", expression

    numerator = quote_identifier(roles[definition.numerator_role or ""])
    denominator = quote_identifier(roles[definition.denominator_role or ""])
    num_sum = f"SUM(TRY_CAST({numerator} AS DOUBLE))"
    if definition.aggregation == "difference":
        den_sum = f"SUM(TRY_CAST({denominator} AS DOUBLE))"
        expression = f"({num_sum} - {den_sum})"
    elif definition.aggregation == "difference_ratio":
        den_sum = f"SUM(TRY_CAST({denominator} AS DOUBLE))"
        expression = f"(({num_sum} - {den_sum}) / NULLIF({num_sum}, 0) * 100)"
    elif definition.aggregation == "sum_per_distinct":
        den_count = f"COUNT(DISTINCT {denominator})"
        expression = f"({num_sum} / NULLIF({den_count}, 0))"
    elif definition.aggregation == "ratio":
        den_sum = f"SUM(TRY_CAST({denominator} AS DOUBLE))"
        expression = f"({num_sum} / NULLIF({den_sum}, 0) * 100)"
    else:
        raise ValueError(f"Unsupported semantic metric aggregation: {definition.aggregation}")
    return f"SELECT {expression} AS {alias} FROM df", expression


def execute_semantic_metrics(
    handle: DatasetHandle,
    roles: Dict[str, str],
    *,
    custom: Optional[Iterable[Dict[str, Any]]] = None,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for definition in resolve_metric_definitions(roles, custom)[:limit]:
        try:
            if definition.aggregation == "dax_subset":
                from app.services.dax_engine import validate_dax_expression

                validation = validate_dax_expression(
                    definition.expression,
                    columns=handle.column_names(),
                    mode="measure",
                )
                if not validation["executable"]:
                    raise ValueError(validation["execution_error"])
                formula = validation["compiled_expression"]
                sql = f'SELECT {formula} AS {quote_identifier(definition.key)} FROM df'
            else:
                sql, formula = metric_sql(definition, roles)
            frame = handle.execute_select(sql, max_rows=2)
            if frame.empty:
                continue
            scalar = pd.to_numeric(frame.iloc[0, 0], errors="coerce")
            if pd.isna(scalar):
                continue
            results.append(
                {
                    "definition": definition.to_dict(),
                    "value": float(scalar),
                    "sql": sql,
                    "formula": formula,
                    "source_columns": [
                        roles[role]
                        for role in (
                            definition.role,
                            definition.numerator_role,
                            definition.denominator_role,
                        )
                        if role and roles.get(role)
                    ],
                }
            )
        except Exception as exc:
            results.append(
                {
                    "definition": definition.to_dict(),
                    "eligible": False,
                    "error": str(exc),
                }
            )
    return results
