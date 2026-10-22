"""Deterministic, provenance-rich findings for compute-first chat responses."""
from __future__ import annotations

import hashlib
import json
import math
import re
import warnings
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from app.services.dataset_engine import DatasetHandle
from app.services.analytical_extensions import (
    compute_drilldown,
    forecast_metric,
    parse_and_run_scenario,
)
from app.services.semantic_metrics import execute_semantic_metrics

Finding = Dict[str, Any]


def _json_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (float, np.floating)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return str(value)


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _finding(
    *,
    kind: str,
    metric: str,
    value: Any,
    unit: str,
    evidence: str,
    engine: str,
    columns: Iterable[str] = (),
    query: Optional[str] = None,
    rows: Optional[int] = None,
    direction: str = "neutral",
    interpretation: str = "",
    suggested_action: str = "",
    eligibility: Optional[Dict[str, Any]] = None,
    period: Optional[str] = None,
    formula: Optional[str] = None,
    filters: Optional[List[str]] = None,
    metric_definition: Optional[Dict[str, Any]] = None,
    audit_details: Optional[Dict[str, Any]] = None,
) -> Finding:
    scalar = _json_scalar(value)
    identity = {
        "kind": kind,
        "metric": metric,
        "value": scalar,
        "unit": unit,
        "columns": list(columns),
        "query": query,
        "period": period,
    }
    return {
        "id": f"f_{_hash(identity)}",
        "type": kind,
        "metric": metric,
        "value": scalar,
        "unit": unit,
        "direction": direction,
        "significance": "descriptive",
        "evidence": evidence,
        "interpretation": interpretation,
        "suggested_action": suggested_action,
        "provenance": {
            "engine": engine,
            "source_columns": list(columns),
            "query_hash": _hash(query) if query else None,
            "result_hash": _hash(scalar),
            "row_count": rows,
            "period": period,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        },
        "eligibility": eligibility or {"eligible": True},
        "audit": {
            "sql": query,
            "formula": formula,
            "filters": filters or [],
            "metric_definition": metric_definition,
            "details": audit_details or {},
        },
    }


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _numeric_columns(sample: pd.DataFrame, roles: Dict[str, str]) -> List[str]:
    preferred_roles = (
        "sales", "revenue", "cost", "quantity", "profit", "margin", "output",
        "ad_spend", "clicks", "impressions", "stock_level", "salary",
    )
    preferred = [
        roles[role] for role in preferred_roles
        if roles.get(role) in sample.columns
        and pd.to_numeric(sample[roles[role]], errors="coerce").notna().any()
    ]
    inferred = [
        col for col in sample.columns
        if pd.to_numeric(sample[col], errors="coerce").notna().mean() >= 0.8
        and not re.search(r"(^id$|_id$|code|phone|zip|year$)", str(col), re.I)
    ]
    return list(dict.fromkeys(preferred + inferred))


def _dimension_columns(sample: pd.DataFrame, roles: Dict[str, str]) -> List[str]:
    preferred_roles = (
        "product", "category", "branch", "region", "country", "channel",
        "department", "supplier", "status", "employee",
    )
    preferred = [roles[role] for role in preferred_roles if roles.get(role) in sample.columns]
    inferred = []
    for col in sample.columns:
        cardinality = sample[col].nunique(dropna=True)
        if 2 <= cardinality <= min(100, max(2, len(sample) // 3)):
            if not pd.api.types.is_numeric_dtype(sample[col]):
                inferred.append(col)
    return list(dict.fromkeys(preferred + inferred))


def _date_column(sample: pd.DataFrame, roles: Dict[str, str]) -> Optional[str]:
    for role in ("date", "timestamp", "created_at"):
        if roles.get(role) in sample.columns:
            return roles[role]
    for col in sample.columns:
        series = sample[col]
        if pd.api.types.is_datetime64_any_dtype(series):
            return col
        name_hint = bool(re.search(r"(date|time|timestamp|month|year|period)", str(col), re.I))
        if not name_hint and not (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
        ):
            continue
        text_sample = series.dropna().astype(str).head(100)
        value_hint = bool(
            len(text_sample)
            and text_sample.str.contains(r"\d{4}[-/]\d{1,2}|T\d{2}:", regex=True).mean()
            >= 0.5
        )
        if not name_hint and not value_hint:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            parsed = pd.to_datetime(series, errors="coerce", utc=True)
        if len(parsed) and parsed.notna().mean() >= 0.8:
            return col
    return None


def _query_scalar(handle: DatasetHandle, sql: str) -> Optional[float]:
    result = handle.execute_select(sql, max_rows=2)
    if result.empty:
        return None
    value = pd.to_numeric(result.iloc[0, 0], errors="coerce")
    return None if pd.isna(value) else float(value)


def build_structured_findings(
    handle: DatasetHandle,
    analytics_results: Optional[Dict[str, Any]] = None,
    *,
    compute_depth: str = "base",
    max_findings: int = 12,
    question: str = "",
) -> List[Finding]:
    """Compute bounded global-business findings without asking an LLM for numbers."""
    if handle.row_count() == 0:
        return []
    roles = dict((analytics_results or {}).get("detected_roles") or {})
    sample_limit = 200_000 if compute_depth == "deep" else 50_000
    sample = handle.to_pandas(limit=min(handle.row_count(), sample_limit))
    rows = handle.row_count()
    engine = "duckdb"
    findings: List[Finding] = [
        _finding(
            kind="dataset_size",
            metric="row_count",
            value=rows,
            unit="rows",
            evidence=f"{rows:,} records are available for analysis.",
            engine=engine,
            rows=rows,
        )
    ]

    missing_cells = int(sample.isna().sum().sum())
    total_cells = max(1, int(sample.shape[0] * sample.shape[1]))
    missing_rate = missing_cells / total_cells * 100
    findings.append(
        _finding(
            kind="data_quality",
            metric="missing_cell_rate",
            value=round(missing_rate, 4),
            unit="%",
            evidence=f"Missing values represent {missing_rate:.2f}% of sampled cells.",
            engine="pandas_sample",
            columns=sample.columns,
            rows=len(sample),
            interpretation="Higher missingness can reduce confidence in segmented comparisons.",
            suggested_action="Review missingness by key dimensions before acting on small differences.",
        )
    )

    semantic_results = execute_semantic_metrics(
        handle,
        roles,
        custom=(analytics_results or {}).get("metric_definitions") or [],
        limit=8,
    )
    semantic_values: Dict[str, float] = {}
    for result in semantic_results:
        definition = result.get("definition") or {}
        if result.get("value") is None:
            continue
        key = str(definition.get("key") or "metric")
        value = float(result["value"])
        semantic_values[key] = value
        findings.append(
            _finding(
                kind="semantic_metric",
                metric=key,
                value=round(value, 6),
                unit=str(definition.get("unit") or "native"),
                evidence=f"{definition.get('label', key)} was computed from the registered metric definition.",
                engine="duckdb_semantic_layer",
                columns=result.get("source_columns") or [],
                query=result.get("sql"),
                formula=result.get("formula"),
                metric_definition=definition,
                rows=rows,
                interpretation=str(definition.get("description") or ""),
            )
        )

    scenario = parse_and_run_scenario(question, semantic_values)
    if scenario:
        scenario_value = scenario.get("projected_profit")
        scenario_metric = "scenario_projected_profit"
        if scenario_value is None:
            scenario_value = scenario.get("projected_revenue")
            scenario_metric = "scenario_projected_revenue"
        findings.append(
            _finding(
                kind="scenario",
                metric=scenario_metric,
                value=round(float(scenario_value), 6),
                unit="native",
                evidence=f"Scenario calculated from explicit assumptions: {scenario.get('assumptions')}.",
                engine="deterministic_scenario",
                columns=[],
                rows=rows,
                formula=scenario.get("formula"),
                audit_details=scenario,
                interpretation="This is a sensitivity result under stated assumptions, not a prediction.",
                suggested_action="Stress-test a conservative and an upside case before using the result.",
            )
        )

    wants_forecast = bool(re.search(r"\b(forecast|predict|projection)\b|พยากรณ์|คาดการณ์", question, re.I))
    if compute_depth == "deep" or wants_forecast:
        forecast = forecast_metric(handle, roles)
        if forecast and forecast.get("eligible") and forecast.get("forecast"):
            first = forecast["forecast"][0]
            findings.append(
                _finding(
                    kind="forecast",
                    metric=f"forecast_{forecast['metric']}",
                    value=round(float(first["value"]), 6),
                    unit="native",
                    evidence=f"Baseline forecast for {first['period']} with a 95% residual interval.",
                    engine="numpy_linear_trend",
                    columns=[forecast["date_column"], forecast["metric"]],
                    rows=rows,
                    period=first["period"],
                    formula="OLS linear trend; interval = prediction ± 1.96 × residual standard deviation",
                    audit_details=forecast,
                    interpretation=forecast["caveat"],
                    suggested_action="Use as a baseline and compare with operational plans and scenarios.",
                    eligibility={
                        "eligible": True,
                        "minimum_periods": 6,
                        "observed_periods": forecast["observed_periods"],
                    },
                )
            )

    wants_drilldown = bool(
        re.search(r"\b(why|driver|contribution|breakdown|drill)\b|ทำไม|สาเหตุ|ปัจจัย|แยก", question, re.I)
    )
    if compute_depth == "deep" or wants_drilldown:
        drilldowns = compute_drilldown(handle, roles)
        for drilldown in drilldowns[:3]:
            if not drilldown.get("drivers"):
                continue
            driver = drilldown["drivers"][0]
            findings.append(
                _finding(
                    kind="drilldown",
                    metric=f"top_{drilldown['dimension']}_driver",
                    value=round(float(driver["delta"]), 6),
                    unit="native",
                    evidence=(
                        f"{driver['segment']} is the largest absolute {drilldown['dimension']} "
                        f"driver from {drilldown['previous_period']} to {drilldown['latest_period']}."
                    ),
                    engine="pandas_drilldown",
                    columns=[drilldown["dimension"], drilldown["metric"]],
                    rows=rows,
                    period=f"{drilldown['previous_period']} to {drilldown['latest_period']}",
                    formula="segment latest-period value - segment previous-period value",
                    audit_details=drilldown,
                    interpretation="This attributes the observed change but does not prove causality.",
                    suggested_action=f"Inspect {driver['segment']} by price, volume, mix, and operational events.",
                )
            )

    numeric = _numeric_columns(sample, roles)
    dimensions = _dimension_columns(sample, roles)
    for col in numeric[:3]:
        q = _quote(col)
        sql = f"SELECT SUM(TRY_CAST({q} AS DOUBLE)) AS value FROM df"
        total = _query_scalar(handle, sql)
        if total is None:
            continue
        findings.append(
            _finding(
                kind="aggregate",
                metric=f"total_{col}",
                value=round(total, 6),
                unit="native",
                evidence=f"Full-dataset total for {col} is {total:,.6g}.",
                engine=engine,
                columns=[col],
                query=sql,
                rows=rows,
            )
        )

    if numeric and dimensions:
        metric, dimension = numeric[0], dimensions[0]
        qm, qd = _quote(metric), _quote(dimension)
        sql = (
            f"WITH grouped AS (SELECT {qd} AS segment, "
            f"SUM(TRY_CAST({qm} AS DOUBLE)) AS amount FROM df GROUP BY 1), "
            "ranked AS (SELECT *, SUM(amount) OVER () AS total_amount, "
            "ROW_NUMBER() OVER (ORDER BY amount DESC) AS rn, COUNT(*) OVER () AS n FROM grouped) "
            "SELECT SUM(CASE WHEN rn <= CEIL(n * 0.2) THEN amount ELSE 0 END) "
            "/ NULLIF(MAX(total_amount), 0) * 100 AS top_20_share FROM ranked"
        )
        share = _query_scalar(handle, sql)
        if share is not None:
            findings.append(
                _finding(
                    kind="pareto",
                    metric=f"top_20pct_{dimension}_share_of_{metric}",
                    value=round(share, 4),
                    unit="%",
                    evidence=f"The top 20% of {dimension} contribute {share:.2f}% of {metric}.",
                    engine=engine,
                    columns=[dimension, metric],
                    query=sql,
                    rows=rows,
                    direction="high" if share >= 80 else "neutral",
                    interpretation="A high share indicates concentration and dependency risk.",
                    suggested_action="Validate whether the leading segments are durable before concentrating resources.",
                )
            )

    date_col = _date_column(sample, roles)
    if date_col and numeric:
        metric = numeric[0]
        dates = pd.to_datetime(sample[date_col], errors="coerce", utc=True)
        values = pd.to_numeric(sample[metric], errors="coerce")
        monthly = (
            pd.DataFrame({"date": dates, "value": values})
            .dropna()
            .set_index("date")["value"]
            .resample("MS")
            .sum()
        )
        if len(monthly) >= 2:
            previous, latest = float(monthly.iloc[-2]), float(monthly.iloc[-1])
            growth = None if previous == 0 else (latest - previous) / abs(previous) * 100
            if growth is not None:
                period = f"{monthly.index[-2].date()} to {monthly.index[-1].date()}"
                findings.append(
                    _finding(
                        kind="growth",
                        metric=f"month_over_month_{metric}",
                        value=round(growth, 4),
                        unit="%",
                        evidence=f"{metric} changed {growth:+.2f}% in the latest sampled month.",
                        engine="pandas_sample",
                        columns=[date_col, metric],
                        rows=len(sample),
                        period=period,
                        direction="up" if growth > 0 else "down" if growth < 0 else "flat",
                        interpretation="The latest period moved relative to its immediate baseline.",
                        suggested_action="Confirm the movement against seasonality and operational events.",
                    )
                )
        if len(monthly) >= 13:
            previous_year, latest = float(monthly.iloc[-13]), float(monthly.iloc[-1])
            yoy = None if previous_year == 0 else (latest - previous_year) / abs(previous_year) * 100
            if yoy is not None:
                findings.append(
                    _finding(
                        kind="growth",
                        metric=f"year_over_year_{metric}",
                        value=round(yoy, 4),
                        unit="%",
                        evidence=f"{metric} changed {yoy:+.2f}% versus the same sampled month one year earlier.",
                        engine="pandas_sample",
                        columns=[date_col, metric],
                        rows=len(sample),
                        period=f"{monthly.index[-13].date()} to {monthly.index[-1].date()}",
                        direction="up" if yoy > 0 else "down" if yoy < 0 else "flat",
                        interpretation="Year-over-year comparison reduces simple seasonal distortion.",
                        suggested_action="Check whether mix, price, volume, or market coverage explains the change.",
                    )
                )
        daily = (
            pd.DataFrame({"date": dates, "value": values})
            .dropna()
            .set_index("date")["value"]
            .resample("W-MON")
            .sum()
        )
        if len(daily) >= 2:
            previous_week, latest_week = float(daily.iloc[-2]), float(daily.iloc[-1])
            wow = None if previous_week == 0 else (latest_week - previous_week) / abs(previous_week) * 100
            if wow is not None:
                findings.append(
                    _finding(
                        kind="growth",
                        metric=f"week_over_week_{metric}",
                        value=round(wow, 4),
                        unit="%",
                        evidence=f"{metric} changed {wow:+.2f}% in the latest sampled week.",
                        engine="pandas_sample",
                        columns=[date_col, metric],
                        rows=len(sample),
                        period=f"{daily.index[-2].date()} to {daily.index[-1].date()}",
                        direction="up" if wow > 0 else "down" if wow < 0 else "flat",
                        interpretation="Weekly changes are timely but may be noisy.",
                        suggested_action="Confirm the movement across multiple weeks before changing strategy.",
                    )
                )
        if compute_depth == "deep" and len(monthly) >= 8:
            values_arr = monthly.to_numpy(dtype=float)
            split = max(3, min(len(values_arr) - 3, int(np.argmax(np.abs(np.cumsum(values_arr - values_arr.mean()))))))
            before = float(np.mean(values_arr[:split]))
            after = float(np.mean(values_arr[split:]))
            change = None if before == 0 else (after - before) / abs(before) * 100
            if change is not None:
                findings.append(
                    _finding(
                        kind="change_point",
                        metric=f"level_shift_{metric}",
                        value=round(change, 4),
                        unit="%",
                        evidence=f"Deterministic CUSUM candidate at {monthly.index[split].date()} changes the mean by {change:+.2f}%.",
                        engine="numpy_cusum",
                        columns=[date_col, metric],
                        rows=len(sample),
                        period=str(monthly.index[split].date()),
                        direction="up" if change > 0 else "down",
                        interpretation="This is a candidate structural break, not proof of causality.",
                        suggested_action="Compare this date with releases, campaigns, pricing, or supply events.",
                        eligibility={"eligible": True, "minimum_periods": 8, "observed_periods": len(monthly)},
                    )
                )
        if compute_depth == "deep" and len(monthly) >= 24:
            month_means = monthly.groupby(monthly.index.month).mean()
            seasonality = float(month_means.max() / max(abs(monthly.mean()), 1e-12) * 100)
            findings.append(
                _finding(
                    kind="seasonality",
                    metric=f"peak_month_index_{metric}",
                    value=round(seasonality, 4),
                    unit="index",
                    evidence=f"Peak calendar-month average is {seasonality:.1f}% of the overall monthly mean.",
                    engine="pandas_sample",
                    columns=[date_col, metric],
                    rows=len(sample),
                    interpretation="Repeated calendar effects may influence period comparisons.",
                    suggested_action="Use seasonally comparable periods for targets and forecasts.",
                    eligibility={"eligible": True, "minimum_periods": 24, "observed_periods": len(monthly)},
                )
            )
        if compute_depth == "deep" and dimensions and len(monthly) >= 2:
            dimension = dimensions[0]
            frame = pd.DataFrame(
                {
                    "date": dates.dt.tz_localize(None).dt.to_period("M"),
                    "value": values,
                    "dimension": sample[dimension].astype(str),
                }
            ).dropna()
            latest_periods = sorted(frame["date"].unique())[-2:]
            if len(latest_periods) == 2:
                pivot = (
                    frame[frame["date"].isin(latest_periods)]
                    .groupby(["dimension", "date"])["value"]
                    .sum()
                    .unstack(fill_value=0)
                )
                pivot["delta"] = pivot.get(latest_periods[1], 0) - pivot.get(latest_periods[0], 0)
                total_delta = float(pivot["delta"].sum())
                if total_delta != 0 and not pivot.empty:
                    leader = pivot["delta"].abs().idxmax()
                    contribution = float(pivot.loc[leader, "delta"] / total_delta * 100)
                    findings.append(
                        _finding(
                            kind="contribution",
                            metric=f"{leader}_contribution_to_{metric}_change",
                            value=round(contribution, 4),
                            unit="%",
                            evidence=f"{leader} accounts for {contribution:+.2f}% of the latest net change in {metric}.",
                            engine="pandas_sample",
                            columns=[date_col, dimension, metric],
                            rows=len(sample),
                            period=f"{latest_periods[0]} to {latest_periods[1]}",
                            direction="up" if contribution > 0 else "down",
                            interpretation="Contribution attributes the observed change; it does not establish causality.",
                            suggested_action="Inspect the contributing segment's volume, price, and mix drivers.",
                        )
                    )

    if compute_depth == "deep" and numeric:
        col = numeric[0]
        positive = pd.to_numeric(sample[col], errors="coerce").dropna()
        positive = positive[positive > 0]
        if len(positive) >= 100:
            first_digits = positive.astype(str).str.replace(r"[^0-9]", "", regex=True).str[0]
            observed = first_digits.value_counts(normalize=True)
            expected = {str(d): math.log10(1 + 1 / d) for d in range(1, 10)}
            mad = float(np.mean([abs(float(observed.get(str(d), 0)) - expected[str(d)]) for d in range(1, 10)]))
            findings.append(
                _finding(
                    kind="benford",
                    metric=f"benford_mad_{col}",
                    value=round(mad, 6),
                    unit="MAD",
                    evidence=f"First-digit Benford mean absolute deviation is {mad:.4f}.",
                    engine="pandas_sample",
                    columns=[col],
                    rows=len(positive),
                    interpretation="Benford deviation is a screening signal, not evidence of fraud.",
                    suggested_action="Investigate only alongside process knowledge and transaction-level controls.",
                    eligibility={"eligible": True, "minimum_positive_values": 100, "observed": len(positive)},
                )
            )

    if compute_depth == "deep" and date_col:
        entity_candidates = [
            col for col in sample.columns
            if re.search(r"(customer|client|account|user|member).*id|(^id_customer$)", str(col), re.I)
        ]
        if entity_candidates:
            entity = entity_candidates[0]
            activity = pd.DataFrame(
                {
                    "entity": sample[entity].astype(str),
                    "period": pd.to_datetime(sample[date_col], errors="coerce", utc=True)
                    .dt.tz_localize(None)
                    .dt.to_period("M"),
                }
            ).dropna().drop_duplicates()
            if activity["period"].nunique() >= 2:
                first = activity.groupby("entity")["period"].min().rename("cohort")
                activity = activity.join(first, on="entity")
                activity["age"] = (
                    activity["period"].astype("int64") - activity["cohort"].astype("int64")
                )
                eligible_entities = set(
                    activity.loc[
                        activity["cohort"] < activity["period"].max(), "entity"
                    ]
                )
                if eligible_entities:
                    retained = activity[
                        activity["entity"].isin(eligible_entities)
                        & (activity["age"] == 1)
                    ]["entity"].nunique()
                    retention = retained / len(eligible_entities) * 100
                    findings.append(
                        _finding(
                            kind="cohort_retention",
                            metric="month_1_entity_retention",
                            value=round(retention, 4),
                            unit="%",
                            evidence=f"{retention:.2f}% of eligible {entity} cohorts return in month 1.",
                            engine="pandas_sample",
                            columns=[entity, date_col],
                            rows=len(sample),
                            interpretation="Retention measures repeated observed activity, not customer satisfaction.",
                            suggested_action="Compare retention across acquisition period, channel, and market.",
                            eligibility={
                                "eligible": True,
                                "eligible_entities": len(eligible_entities),
                                "minimum_periods": 2,
                            },
                        )
                    )

    return findings[: max(1, max_findings)]


def build_analysis_eligibility(
    handle: DatasetHandle,
    analytics_results: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Explain which advanced analyses are safe to run and why."""
    sample = handle.to_pandas(limit=min(handle.row_count(), 50_000))
    roles = dict((analytics_results or {}).get("detected_roles") or {})
    numeric = _numeric_columns(sample, roles)
    dimensions = _dimension_columns(sample, roles)
    date_col = _date_column(sample, roles)
    periods = 0
    if date_col:
        parsed = pd.to_datetime(sample[date_col], errors="coerce", utc=True)
        periods = int(parsed.dt.tz_localize(None).dt.to_period("M").nunique())
    positive_values = 0
    if numeric:
        values = pd.to_numeric(sample[numeric[0]], errors="coerce")
        positive_values = int((values > 0).sum())
    entity_candidates = [
        col for col in sample.columns
        if re.search(r"(customer|client|account|user|member).*id|(^id_customer$)", str(col), re.I)
    ]
    return {
        "pareto": {
            "eligible": bool(numeric and dimensions),
            "requires": "at least one numeric metric and one categorical dimension",
        },
        "change_point": {
            "eligible": bool(date_col and numeric and periods >= 8),
            "requires": "date, numeric metric, and at least 8 monthly periods",
            "observed_periods": periods,
        },
        "seasonality": {
            "eligible": bool(date_col and numeric and periods >= 24),
            "requires": "date, numeric metric, and at least 24 monthly periods",
            "observed_periods": periods,
        },
        "contribution": {
            "eligible": bool(date_col and numeric and dimensions and periods >= 2),
            "requires": "date, numeric metric, dimension, and at least 2 periods",
        },
        "cohort_retention": {
            "eligible": bool(date_col and entity_candidates and periods >= 2),
            "requires": "customer/user identifier, activity date, and at least 2 periods",
            "entity_column": entity_candidates[0] if entity_candidates else None,
        },
        "benford": {
            "eligible": positive_values >= 100,
            "requires": "at least 100 positive values in a suitable numeric measure",
            "observed_positive_values": positive_values,
        },
    }


def build_column_intelligence(
    handle: DatasetHandle,
    analytics_results: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sample = handle.to_pandas(limit=min(handle.row_count(), 20_000))
    roles = dict((analytics_results or {}).get("detected_roles") or {})
    columns = []
    reverse_roles = {column: role for role, column in roles.items()}
    for col in sample.columns:
        non_null = sample[col].dropna()
        columns.append(
            {
                "name": str(col),
                "semantic_role": reverse_roles.get(col),
                "dtype": str(sample[col].dtype),
                "null_rate": round(float(sample[col].isna().mean() * 100), 4),
                "distinct_count_sample": int(non_null.nunique()),
                "likely_identifier": bool(
                    len(non_null)
                    and non_null.nunique() / len(non_null) >= 0.98
                    and re.search(r"(^id$|_id$|code|number|key)", str(col), re.I)
                ),
            }
        )
    return {
        "sample_rows": len(sample),
        "dataset_rows": handle.row_count(),
        "columns": columns[:50],
        "column_count": len(columns),
        "columns_truncated": len(columns) > 50,
        "grain_candidates": [
            item["name"] for item in columns if item["likely_identifier"]
        ][:5],
    }


def finding_from_query_result(
    question: str,
    sql: str,
    result: pd.DataFrame,
    *,
    rows_analyzed: int,
    template_id: Optional[str] = None,
) -> List[Finding]:
    findings: List[Finding] = []
    if result.empty:
        return findings
    numeric_cols = [c for c in result.columns if pd.to_numeric(result[c], errors="coerce").notna().any()]
    if len(result) == 1:
        for col in numeric_cols[:4]:
            value = pd.to_numeric(result.iloc[0][col], errors="coerce")
            if pd.isna(value):
                continue
            findings.append(
                _finding(
                    kind="question_metric",
                    metric=str(col),
                    value=float(value),
                    unit="native",
                    evidence=f"Computed for question: {question}",
                    engine="duckdb_template" if template_id else "duckdb_llm_sql",
                    columns=result.columns,
                    query=sql,
                    rows=rows_analyzed,
                )
            )
    return findings


def build_response_outline(findings: List[Finding], *, compute_depth: str) -> str:
    if not findings:
        return ""
    useful = [
        finding for finding in findings
        if finding.get("type") not in {"dataset_size"} and finding.get("value") is not None
    ][:6]
    if not useful:
        useful = findings[:3]
    lines = [
        "### Verified analysis",
        "",
        f"_Server-computed · {compute_depth.title()} compute · {len(findings)} verified findings_",
        "",
        "| Metric | Value | Evidence |",
        "|---|---:|---|",
    ]
    for item in useful:
        value = item.get("value")
        rendered = f"{value:,.4g}" if isinstance(value, (float, int)) else str(value)
        unit = item.get("unit")
        if unit and unit not in {"native", "index", "rows"}:
            rendered = f"{rendered}{unit}" if unit == "%" else f"{rendered} {unit}"
        elif unit == "rows":
            rendered = f"{rendered} rows"
        evidence = str(item.get("evidence") or "").replace("|", "\\|")
        lines.append(f"| {item.get('metric')} | {rendered} | {evidence} |")
    lines.extend(["", "### Interpretation", ""])
    return "\n".join(lines)
