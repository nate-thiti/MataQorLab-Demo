"""Grain, drill-down, forecasting, and scenario engines for analytical chat."""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from app.services.dataset_engine import DatasetHandle


def infer_grain_and_join_risks(
    handle: DatasetHandle,
    roles: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    roles = roles or {}
    sample = handle.to_pandas(limit=min(handle.row_count(), 50_000))
    rows = len(sample)
    candidates: List[Dict[str, Any]] = []
    for col in sample.columns:
        non_null = sample[col].dropna()
        distinct = int(non_null.nunique())
        uniqueness = distinct / max(1, len(non_null))
        if uniqueness >= 0.9 or col in roles.values():
            candidates.append(
                {
                    "columns": [str(col)],
                    "distinct_sample": distinct,
                    "uniqueness": round(uniqueness, 6),
                    "null_rate": round(float(sample[col].isna().mean() * 100), 4),
                    "likely_key": uniqueness >= 0.98 and sample[col].isna().sum() == 0,
                }
            )
    candidates.sort(key=lambda item: (item["likely_key"], item["uniqueness"]), reverse=True)
    primary = next((item for item in candidates if item["likely_key"]), None)
    warnings: List[str] = []
    order_col = roles.get("order_id")
    line_col = roles.get("line_id")
    if order_col and order_col in sample:
        orders = max(1, sample[order_col].nunique(dropna=True))
        lines_per_order = rows / orders
        if lines_per_order > 1.05:
            warnings.append(
                f"Dataset appears to be order-line grain ({lines_per_order:.2f} rows per order); "
                "counting rows as orders would overstate order volume."
            )
    if not primary:
        warnings.append("No single-column unique key was found in the sample; joins require explicit cardinality checks.")
    return {
        "row_count": handle.row_count(),
        "sample_rows": rows,
        "grain": "order_line" if order_col and (line_col or any("rows per order" in w for w in warnings)) else "row",
        "primary_key_candidate": primary,
        "key_candidates": candidates[:8],
        "join_risks": warnings,
    }


def assess_join_cardinality(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_key: str,
    right_key: Optional[str] = None,
) -> Dict[str, Any]:
    right_key = right_key or left_key
    left_counts = left[left_key].value_counts(dropna=False)
    right_counts = right[right_key].value_counts(dropna=False)
    left_many = bool((left_counts > 1).any())
    right_many = bool((right_counts > 1).any())
    cardinality = (
        "many_to_many" if left_many and right_many
        else "many_to_one" if left_many
        else "one_to_many" if right_many
        else "one_to_one"
    )
    shared = set(left_counts.index) & set(right_counts.index)
    estimated_rows = int(sum(int(left_counts[key]) * int(right_counts[key]) for key in shared))
    baseline = max(len(left), len(right), 1)
    multiplier = estimated_rows / baseline
    return {
        "cardinality": cardinality,
        "estimated_join_rows": estimated_rows,
        "row_multiplier": round(multiplier, 6),
        "safe": cardinality != "many_to_many" and multiplier <= 1.25,
        "warning": (
            "Many-to-many join can duplicate measures; aggregate or deduplicate before joining."
            if cardinality == "many_to_many"
            else "Join may expand row count; verify the intended grain."
            if multiplier > 1.25
            else ""
        ),
    }


def compute_drilldown(
    handle: DatasetHandle,
    roles: Dict[str, str],
    *,
    max_dimensions: int = 5,
) -> List[Dict[str, Any]]:
    sample = handle.to_pandas(limit=min(handle.row_count(), 100_000))
    date_col = roles.get("date") or roles.get("timestamp")
    metric_col = next(
        (roles.get(role) for role in ("sales", "profit", "cost", "quantity", "output") if roles.get(role)),
        None,
    )
    dimensions = [
        roles[role]
        for role in ("country", "region", "market", "channel", "product", "category", "branch", "department", "supplier")
        if roles.get(role) in sample.columns
    ]
    if not date_col or not metric_col or date_col not in sample or metric_col not in sample:
        return []
    dates = pd.to_datetime(sample[date_col], errors="coerce", utc=True)
    periods = dates.dt.tz_localize(None).dt.to_period("M")
    values = pd.to_numeric(sample[metric_col], errors="coerce")
    frame = pd.DataFrame({"period": periods, "value": values}).dropna()
    unique_periods = sorted(frame["period"].unique())
    if len(unique_periods) < 2:
        return []
    previous, latest = unique_periods[-2:]
    total_delta = float(
        frame.loc[frame["period"] == latest, "value"].sum()
        - frame.loc[frame["period"] == previous, "value"].sum()
    )
    results: List[Dict[str, Any]] = []
    for dimension in list(dict.fromkeys(dimensions))[:max_dimensions]:
        dim_frame = pd.DataFrame(
            {"period": periods, "value": values, "segment": sample[dimension].astype(str)}
        ).dropna()
        pivot = (
            dim_frame[dim_frame["period"].isin([previous, latest])]
            .groupby(["segment", "period"])["value"]
            .sum()
            .unstack(fill_value=0)
        )
        pivot["delta"] = pivot.get(latest, 0) - pivot.get(previous, 0)
        if pivot.empty:
            continue
        ranked = pivot.reindex(pivot["delta"].abs().sort_values(ascending=False).index).head(5)
        results.append(
            {
                "dimension": dimension,
                "metric": metric_col,
                "previous_period": str(previous),
                "latest_period": str(latest),
                "total_delta": total_delta,
                "drivers": [
                    {
                        "segment": str(index),
                        "delta": float(row["delta"]),
                        "contribution_pct": (
                            float(row["delta"] / total_delta * 100) if total_delta else None
                        ),
                    }
                    for index, row in ranked.iterrows()
                ],
            }
        )
    return results


def forecast_metric(
    handle: DatasetHandle,
    roles: Dict[str, str],
    *,
    horizon: int = 3,
) -> Optional[Dict[str, Any]]:
    sample = handle.to_pandas(limit=min(handle.row_count(), 200_000))
    date_col = roles.get("date") or roles.get("timestamp")
    metric_col = next((roles.get(r) for r in ("sales", "profit", "quantity", "cost") if roles.get(r)), None)
    if not date_col or not metric_col or date_col not in sample or metric_col not in sample:
        return None
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(sample[date_col], errors="coerce", utc=True),
            "value": pd.to_numeric(sample[metric_col], errors="coerce"),
        }
    ).dropna()
    monthly = frame.set_index("date")["value"].resample("MS").sum()
    if len(monthly) < 6:
        return {
            "eligible": False,
            "reason": "Forecast requires at least 6 monthly periods.",
            "observed_periods": len(monthly),
        }
    x = np.arange(len(monthly), dtype=float)
    slope, intercept = np.polyfit(x, monthly.to_numpy(dtype=float), 1)
    fitted = intercept + slope * x
    residual_std = float(np.std(monthly.to_numpy(dtype=float) - fitted, ddof=1))
    future_x = np.arange(len(monthly), len(monthly) + horizon, dtype=float)
    future_index = pd.date_range(monthly.index[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    predictions = intercept + slope * future_x
    interval = 1.96 * residual_std
    return {
        "eligible": True,
        "method": "linear_trend_with_residual_interval",
        "metric": metric_col,
        "date_column": date_col,
        "observed_periods": len(monthly),
        "horizon": horizon,
        "slope_per_month": float(slope),
        "forecast": [
            {
                "period": period.date().isoformat(),
                "value": float(value),
                "lower_95": float(value - interval),
                "upper_95": float(value + interval),
            }
            for period, value in zip(future_index, predictions)
        ],
        "caveat": "Statistical baseline only; it assumes the historical linear trend persists.",
    }


def parse_and_run_scenario(
    question: str,
    semantic_values: Dict[str, float],
) -> Optional[Dict[str, Any]]:
    text = (question or "").lower()
    if not re.search(r"\b(if|scenario|what[- ]if)\b|ถ้า|สมมติ", text):
        return None
    changes: Dict[str, float] = {}
    aliases = {
        "price": ("price", "ราคา"),
        "volume": ("volume", "units", "quantity", "จำนวน", "ยอดขายเชิงปริมาณ"),
        "cost": ("cost", "ต้นทุน"),
        "revenue": ("revenue", "sales", "รายได้", "ยอดขาย"),
    }
    for key, terms in aliases.items():
        for term in terms:
            match = re.search(
                rf"{re.escape(term)}[^\d+\-]{{0,18}}([+\-]?\d+(?:\.\d+)?)\s*%",
                text,
            )
            if match:
                value = float(match.group(1))
                context = match.group(0)
                if value > 0 and re.search(r"\b(decrease|decreases|decreased|drop|drops|down|lower)\b|ลด|ต่ำลง", context):
                    value = -value
                changes[key] = value
                break
            match = re.search(
                rf"([+\-]?\d+(?:\.\d+)?)\s*%[^\n,.]{{0,18}}{re.escape(term)}",
                text,
            )
            if match:
                value = float(match.group(1))
                context = match.group(0)
                if value > 0 and re.search(r"\b(decrease|decreases|decreased|drop|drops|down|lower)\b|ลด|ต่ำลง", context):
                    value = -value
                changes[key] = value
                break
    baseline_revenue = semantic_values.get("revenue")
    baseline_cost = semantic_values.get("cost")
    if not changes or baseline_revenue is None:
        return None
    revenue_factor = 1.0
    for key in ("price", "volume", "revenue"):
        if key in changes:
            revenue_factor *= 1 + changes[key] / 100
    projected_revenue = baseline_revenue * revenue_factor
    projected_cost = (
        baseline_cost * (1 + changes.get("cost", 0) / 100)
        if baseline_cost is not None
        else None
    )
    baseline_profit = baseline_revenue - baseline_cost if baseline_cost is not None else None
    projected_profit = projected_revenue - projected_cost if projected_cost is not None else None
    return {
        "assumptions": changes,
        "baseline_revenue": baseline_revenue,
        "projected_revenue": projected_revenue,
        "revenue_delta": projected_revenue - baseline_revenue,
        "baseline_profit": baseline_profit,
        "projected_profit": projected_profit,
        "profit_delta": (
            projected_profit - baseline_profit
            if projected_profit is not None and baseline_profit is not None
            else None
        ),
        "formula": "Revenue' = Revenue × Π(1 + assumption%); Profit' = Revenue' - Cost'",
        "caveat": "Deterministic sensitivity scenario, not a causal forecast.",
    }
