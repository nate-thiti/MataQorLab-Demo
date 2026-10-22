"""Deterministic, user-approved ETL recipe helpers.

The LLM may explain recommendations, but only this module mutates tabular data.
Every mutation is explicit in the recipe and returned in the audit report.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.core.json_safety import to_json_safe

RECIPE_VERSION = "etl_recipe_v1"
DATA_CONTRACT_VERSION = "2.0"
CRITICAL_ROLES = {
    "sales", "revenue", "cost", "profit", "id", "order_id", "customer_id",
    "date", "timestamp", "due_date",
}
IMPUTE_METHODS = {"median", "mean", "mode", "forward_fill", "backward_fill", "constant"}
OUTLIER_ACTIONS = {"flag", "exclude", "delete", "winsorize", "keep"}
TRANSFORM_TYPES = {"rename", "type_cast", "derived", "dax_calculated", "filter"}
SAFE_COLUMN_RE = re.compile(r"^[A-Za-z0-9_\-\u0E00-\u0E7F .]+$")
DATA_CONTRACT_TEXT_FIELDS = {
    "data_owner",
    "data_steward",
    "owner_contact",
    "business_purpose",
    "row_grain",
    "metric_definition",
    "cancellation_policy",
    "null_policy",
    "duplicate_policy",
    "context_notes",
    "timezone",
    "currency",
    "revenue_basis",
    "fiscal_year_start",
    "reporting_start",
    "reporting_end",
    "as_of_date",
    "freshness_sla",
    "retention_policy",
    "reviewed_by",
    "reviewed_at",
}
PERIOD_STATUSES = {"complete", "in_progress", "unknown"}
UPDATE_FREQUENCIES = {
    "realtime", "hourly", "daily", "weekly", "monthly", "quarterly", "ad_hoc", "unknown",
}
DATA_CLASSIFICATIONS = {"public", "internal", "confidential", "restricted"}
ENFORCEMENT_MODES = {"warn", "strict"}
AGGREGATIONS = {"sum", "avg", "min", "max", "count", "count_distinct", "none"}
SENSITIVITY_LEVELS = {"none", "personal", "sensitive", "restricted"}
UNIQUE_ANALYTICAL_ROLES = {
    "sales", "revenue", "cost", "profit", "quantity", "price", "discount",
    "order_id", "invoice_id", "line_id", "customer_id", "date", "timestamp",
}


def _bounded_string_list(value: Any, *, limit: int = 100) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value[:limit]:
        text = str(item or "").strip()[:500]
        if text and text not in result:
            result.append(text)
    return result


def _normalize_column_contracts(value: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for raw_column, raw_spec in list(value.items())[:500]:
        column = str(raw_column or "").strip()[:300]
        if not column or not isinstance(raw_spec, dict):
            continue
        aggregation = str(raw_spec.get("aggregation") or "none").strip().lower()
        sensitivity = str(raw_spec.get("sensitivity") or "none").strip().lower()
        result[column] = {
            "business_name": str(raw_spec.get("business_name") or "").strip()[:300],
            "description": str(raw_spec.get("description") or "").strip()[:1000],
            "data_type": str(raw_spec.get("data_type") or "").strip().lower()[:80],
            "unit": str(raw_spec.get("unit") or "").strip()[:80],
            "aggregation": aggregation if aggregation in AGGREGATIONS else "none",
            "sensitivity": (
                sensitivity if sensitivity in SENSITIVITY_LEVELS else "none"
            ),
            "required": bool(raw_spec.get("required")),
            "unique": bool(raw_spec.get("unique")),
            "allowed_values": _bounded_string_list(
                raw_spec.get("allowed_values"), limit=100
            ),
        }
    return result


def _normalize_metric_definitions(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: List[Dict[str, Any]] = []
    for raw in value[:100]:
        if not isinstance(raw, dict):
            continue
        aggregation = str(raw.get("aggregation") or "sum").strip().lower()
        name = str(raw.get("name") or "").strip()[:200]
        if not name:
            continue
        result.append({
            "name": name,
            "source_column": str(raw.get("source_column") or "").strip()[:300],
            "aggregation": aggregation if aggregation in AGGREGATIONS else "sum",
            "definition": str(raw.get("definition") or "").strip()[:1000],
            "unit": str(raw.get("unit") or "").strip()[:80],
        })
    return result


def _normalize_causal_design(value: Any) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    text_fields = (
        "date_column",
        "outcome_column",
        "intervention_date",
        "treatment_column",
        "treatment_value",
        "control_value",
        "group_column",
    )
    return {
        **{
            key: str(raw.get(key) or "").strip()[:300]
            for key in text_fields
        },
        "predictor_columns": _bounded_string_list(
            raw.get("predictor_columns"), limit=50
        ),
        "known_confounders": _bounded_string_list(
            raw.get("known_confounders"), limit=50
        ),
    }


def normalize_data_contract(value: Any) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    contract = {
        key: str(raw.get(key) or "").strip()[:1000]
        for key in DATA_CONTRACT_TEXT_FIELDS
    }
    period_status = str(raw.get("period_status") or "unknown").strip().lower()
    contract["period_status"] = (
        period_status if period_status in PERIOD_STATUSES else "unknown"
    )
    contract["mapping_confirmed"] = bool(raw.get("mapping_confirmed"))
    contract["business_context_reviewed"] = bool(
        raw.get("business_context_reviewed")
    )
    update_frequency = str(raw.get("update_frequency") or "unknown").strip().lower()
    contract["update_frequency"] = (
        update_frequency if update_frequency in UPDATE_FREQUENCIES else "unknown"
    )
    classification = str(
        raw.get("data_classification") or "internal"
    ).strip().lower()
    contract["data_classification"] = (
        classification if classification in DATA_CLASSIFICATIONS else "internal"
    )
    enforcement = str(raw.get("enforcement_mode") or "warn").strip().lower()
    contract["enforcement_mode"] = (
        enforcement if enforcement in ENFORCEMENT_MODES else "warn"
    )
    currency = contract.get("currency", "").upper()
    contract["currency"] = currency if re.fullmatch(r"[A-Z]{3}", currency) else ""
    contract["contract_version"] = DATA_CONTRACT_VERSION
    contract["primary_keys"] = _bounded_string_list(raw.get("primary_keys"))
    contract["decisions_supported"] = _bounded_string_list(
        raw.get("decisions_supported")
    )
    contract["inclusions"] = _bounded_string_list(raw.get("inclusions"))
    contract["exclusions"] = _bounded_string_list(raw.get("exclusions"))
    contract["known_caveats"] = _bounded_string_list(raw.get("known_caveats"))
    contract["column_contracts"] = _normalize_column_contracts(
        raw.get("column_contracts")
    )
    contract["metric_definitions"] = _normalize_metric_definitions(
        raw.get("metric_definitions")
    )
    contract["causal_design"] = _normalize_causal_design(
        raw.get("causal_design")
    )
    return contract


def validate_data_contract(
    value: Any,
    mapping: Optional[Dict[str, str]] = None,
    columns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return deterministic readiness checks without pretending to verify business truth."""
    contract = normalize_data_contract(value)
    mapped = {
        str(column): str(role).strip().lower()
        for column, role in (mapping or {}).items()
        if str(role or "").strip()
    }
    available = {str(column) for column in (columns or list(mapped.keys()))}
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    missing_mapping_columns = sorted(set(mapped) - available)
    if missing_mapping_columns:
        errors.append({
            "code": "mapping_columns_missing",
            "message": "Mapped columns are not present in the source.",
            "fields": ", ".join(missing_mapping_columns[:20]),
        })
    missing_keys = sorted(set(contract["primary_keys"]) - available)
    if missing_keys:
        errors.append({
            "code": "primary_keys_missing",
            "message": "Primary-key columns are not present in the source.",
            "fields": ", ".join(missing_keys[:20]),
        })
    causal_design = contract.get("causal_design") or {}
    causal_columns = {
        causal_design.get("date_column"),
        causal_design.get("outcome_column"),
        causal_design.get("treatment_column"),
        causal_design.get("group_column"),
        *(causal_design.get("predictor_columns") or []),
    }
    missing_causal_columns = sorted(
        str(column) for column in causal_columns
        if column and str(column) not in available
    )
    if missing_causal_columns:
        errors.append({
            "code": "causal_design_columns_missing",
            "message": "Causal-design columns are not present in the source.",
            "fields": ", ".join(missing_causal_columns[:20]),
        })

    role_columns: Dict[str, List[str]] = {}
    for column, role in mapped.items():
        role_columns.setdefault(role, []).append(column)
    ambiguous_roles = {
        role: role_cols
        for role, role_cols in role_columns.items()
        if role in UNIQUE_ANALYTICAL_ROLES and len(role_cols) > 1
    }
    if ambiguous_roles:
        errors.append({
            "code": "ambiguous_semantic_roles",
            "message": "Choose one primary column for each unique analytical role.",
            "fields": "; ".join(
                f"{role}: {', '.join(role_cols)}"
                for role, role_cols in sorted(ambiguous_roles.items())
            )[:1000],
        })

    if (
        contract["reporting_start"]
        and contract["reporting_end"]
        and contract["reporting_start"] > contract["reporting_end"]
    ):
        errors.append({
            "code": "invalid_reporting_period",
            "message": "Reporting start must not be after reporting end.",
            "fields": "reporting_start, reporting_end",
        })

    metric_sources = {
        item["source_column"]
        for item in contract["metric_definitions"]
        if item.get("source_column")
    }
    missing_metric_sources = sorted(metric_sources - available)
    if missing_metric_sources:
        errors.append({
            "code": "metric_columns_missing",
            "message": "Metric definitions reference columns not present in the source.",
            "fields": ", ".join(missing_metric_sources[:20]),
        })

    checks = {
        "mapping_present": bool(mapped),
        "mapping_confirmed": contract["mapping_confirmed"],
        "data_owner_recorded": bool(contract["data_owner"]),
        "business_purpose_recorded": bool(contract["business_purpose"]),
        "row_grain_recorded": bool(contract["row_grain"]),
        "metric_definition_recorded": bool(
            contract["metric_definition"] or contract["metric_definitions"]
        ),
        "period_status_reviewed": contract["period_status"] != "unknown",
        "business_context_reviewed": contract["business_context_reviewed"],
    }
    weights = {
        "mapping_present": 15,
        "mapping_confirmed": 15,
        "data_owner_recorded": 10,
        "business_purpose_recorded": 15,
        "row_grain_recorded": 15,
        "metric_definition_recorded": 15,
        "period_status_reviewed": 5,
        "business_context_reviewed": 10,
    }
    score = sum(weight for key, weight in weights.items() if checks[key])
    missing = [key for key, passed in checks.items() if not passed]
    if contract["business_context_reviewed"] and missing:
        warnings.append({
            "code": "review_incomplete",
            "message": "Business context was marked reviewed while required definitions remain incomplete.",
            "fields": ", ".join(missing),
        })
    status = (
        "invalid" if errors else "ready" if not missing and score == 100 else "needs_review"
    )
    return {
        "contract_version": DATA_CONTRACT_VERSION,
        "status": status,
        "score": score,
        "checks": checks,
        "missing": missing,
        "errors": errors,
        "warnings": warnings,
    }


def recipe_hash(recipe: Optional[Dict[str, Any]]) -> str:
    payload = json.dumps(recipe or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def effective_mapping_for_contract(
    mapping: Optional[Dict[str, str]],
    contract_value: Any,
) -> Dict[str, str]:
    """Resolve the governed revenue column to the canonical analytics role.

    The original source column remains unchanged. Only semantic resolution is
    overridden so Chat, KPI calculation and visualization all use the revenue
    basis explicitly approved in the Data Contract.
    """
    result = {
        str(column): str(role).strip().lower()
        for column, role in (mapping or {}).items()
        if str(role or "").strip()
    }
    contract = normalize_data_contract(contract_value)
    basis = contract.get("revenue_basis") or ""
    preferred = (
        ("gross_amount", "sales", "revenue", "net_amount")
        if basis == "gross"
        else ("net_amount", "sales", "revenue", "gross_amount")
    )
    metric_sources = [
        item.get("source_column")
        for item in contract.get("metric_definitions") or []
        if item.get("source_column")
    ]
    selected = next((column for column in metric_sources if column in result), None)
    if not selected:
        selected = next(
            (column for role in preferred for column, mapped in result.items() if mapped == role),
            None,
        )
    if selected:
        for column, role in list(result.items()):
            if role == "sales" and column != selected:
                result[column] = "gross_amount" if basis == "net" else "net_amount"
        result[selected] = "sales"
    return result


def normalize_recipe(recipe: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = recipe if isinstance(recipe, dict) else {}
    rules = raw.get("rules") if isinstance(raw.get("rules"), dict) else {}
    imputations = raw.get("imputations") if isinstance(raw.get("imputations"), list) else []
    outliers = raw.get("outliers") if isinstance(raw.get("outliers"), list) else []
    invalid_dates = raw.get("invalid_dates") if isinstance(raw.get("invalid_dates"), list) else []
    transforms = raw.get("transformations") if isinstance(raw.get("transformations"), list) else []
    quality_rules = raw.get("quality_rules") if isinstance(raw.get("quality_rules"), list) else []
    issue_resolutions = (
        raw.get("setup_issue_resolutions")
        if isinstance(raw.get("setup_issue_resolutions"), dict)
        else {}
    )
    normalized = {
        "version": RECIPE_VERSION,
        "apply": bool(raw.get("apply", True)),
        "cleaning_profile": str(raw.get("cleaning_profile") or "standard"),
        "column_mapping": {
            str(k): str(v) for k, v in (raw.get("column_mapping") or {}).items()
            if isinstance(k, str) and isinstance(v, str)
        } if isinstance(raw.get("column_mapping"), dict) else {},
        "rules": {str(k): v for k, v in rules.items() if isinstance(v, bool)},
        "imputations": [x for x in imputations if isinstance(x, dict)][:100],
        "outliers": [x for x in outliers if isinstance(x, dict)][:100],
        "invalid_dates": [x for x in invalid_dates if isinstance(x, dict)][:100],
        "transformations": [x for x in transforms if isinstance(x, dict)][:100],
        "quality_rules": [x for x in quality_rules if isinstance(x, dict)][:100],
        "setup_issue_resolutions": {
            str(key)[:350]: str(value)[:100]
            for key, value in list(issue_resolutions.items())[:500]
            if isinstance(key, str) and isinstance(value, (str, int, float, bool))
        },
        # Set only on an immutable ETL output handed to analysis consumers.
        # It prevents applying mutation rules twice to an already prepared file.
        "materialized_prepared": bool(raw.get("materialized_prepared", False)),
        "data_contract": normalize_data_contract(raw.get("data_contract")),
    }
    normalized["contract_validation"] = validate_data_contract(
        normalized["data_contract"],
        normalized["column_mapping"],
        list(normalized["column_mapping"].keys()),
    )
    return normalized


def _role(mapping: Optional[Dict[str, str]], column: str) -> str:
    return str((mapping or {}).get(column) or "").strip().lower()


def missing_value_recommendations(
    df: pd.DataFrame,
    mapping: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    recommendations: List[Dict[str, Any]] = []
    total = max(len(df), 1)
    for col in df.columns:
        missing = int(df[col].isna().sum())
        if not missing:
            continue
        inferred_numeric = pd.api.types.is_numeric_dtype(df[col])
        role = _role(mapping, str(col))
        critical = role in CRITICAL_ROLES
        if critical:
            method = "review"
            reason = "Business-critical field; explicit review is required."
        elif inferred_numeric:
            method = "median"
            reason = "Median is robust to skew and outliers."
        elif df[col].nunique(dropna=True) <= max(20, int(total * 0.1)):
            method = "mode"
            reason = "Categorical field with a stable most-common value."
        else:
            method = "constant"
            reason = "Preserve missingness with an explicit label."
        recommendations.append({
            "column": str(col),
            "missing_count": missing,
            "missing_rate": round(missing / total, 4),
            "recommended_method": method,
            "requires_confirmation": True,
            "critical": critical,
            "reason": reason,
        })
    return recommendations


def detect_outliers(
    df: pd.DataFrame,
    *,
    mapping: Optional[Dict[str, str]] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for col in df.select_dtypes(include="number").columns:
        values = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(values) < 8:
            continue
        q1, q3 = values.quantile([0.25, 0.75])
        iqr = float(q3 - q1)
        median = float(values.median())
        mad = float((values - median).abs().median())
        if iqr == 0 and mad == 0:
            if values.nunique(dropna=True) <= 1:
                continue
            lower = upper = median
        else:
            lower = float(q1 - 1.5 * iqr) if iqr else median - 3.5 * mad
            upper = float(q3 + 1.5 * iqr) if iqr else median + 3.5 * mad
        mask = (pd.to_numeric(df[col], errors="coerce") < lower) | (
            pd.to_numeric(df[col], errors="coerce") > upper
        )
        indexes = [int(i) if isinstance(i, (int, np.integer)) else str(i) for i in df.index[mask][:limit]]
        count = int(mask.sum())
        if count:
            results.append({
                "column": str(col),
                "semantic_role": _role(mapping, str(col)) or None,
                "method": "iqr",
                "lower_bound": round(lower, 6),
                "upper_bound": round(upper, 6),
                "count": count,
                "rate": round(count / max(len(df), 1), 4),
                "sample_indexes": indexes,
                "default_action": "flag",
            })
    return results


def _apply_imputation(
    work: pd.DataFrame,
    spec: Dict[str, Any],
    mapping: Optional[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    col = str(spec.get("column") or "")
    method = str(spec.get("method") or "").lower()
    if col not in work.columns or method not in IMPUTE_METHODS:
        return None
    role = _role(mapping, col)
    if role in CRITICAL_ROLES and not bool(spec.get("confirmed")):
        return {"column": col, "method": method, "changed": 0, "skipped": "confirmation_required"}
    missing_before = int(work[col].isna().sum())
    if not missing_before:
        return {"column": col, "method": method, "changed": 0}
    if method == "median":
        value = pd.to_numeric(work[col], errors="coerce").median()
        work[col] = work[col].fillna(value)
    elif method == "mean":
        value = pd.to_numeric(work[col], errors="coerce").mean()
        work[col] = work[col].fillna(value)
    elif method == "mode":
        modes = work[col].mode(dropna=True)
        value = modes.iloc[0] if not modes.empty else spec.get("value", "Unknown")
        work[col] = work[col].fillna(value)
    elif method == "forward_fill":
        work[col] = work[col].ffill()
    elif method == "backward_fill":
        work[col] = work[col].bfill()
    else:
        work[col] = work[col].fillna(spec.get("value", "Unknown"))
    changed = missing_before - int(work[col].isna().sum())
    flag_col = f"{col}__imputed"
    if changed:
        original_missing = work[col].index.to_series().isin([])
        # Rebuild the flag from the original positions supplied by the caller.
        original_missing = spec.get("_missing_mask")
        if isinstance(original_missing, pd.Series):
            work[flag_col] = original_missing.reindex(work.index, fill_value=False).astype(bool)
    return {"column": col, "method": method, "changed": changed, "flag_column": flag_col if changed else None}


def _apply_transform(work: pd.DataFrame, spec: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    kind = str(spec.get("type") or "")
    if kind not in TRANSFORM_TYPES:
        return work, {"type": kind, "status": "skipped", "reason": "unsupported"}
    col = str(spec.get("column") or "")
    if col and (not SAFE_COLUMN_RE.match(col) or col not in work.columns):
        return work, {"type": kind, "status": "skipped", "reason": "invalid_column"}
    if kind == "rename":
        target = str(spec.get("to") or "").strip()
        if not target or not SAFE_COLUMN_RE.match(target) or target in work.columns:
            return work, {"type": kind, "status": "skipped", "reason": "invalid_target"}
        return work.rename(columns={col: target}), {"type": kind, "column": col, "to": target, "status": "applied"}
    if kind == "type_cast":
        target = str(spec.get("to") or "")
        if target == "numeric":
            work[col] = pd.to_numeric(work[col], errors="coerce")
        elif target == "date":
            work[col] = pd.to_datetime(work[col], errors="coerce")
        elif target == "text":
            work[col] = work[col].astype("string")
        else:
            return work, {"type": kind, "status": "skipped", "reason": "invalid_type"}
        return work, {"type": kind, "column": col, "to": target, "status": "applied"}
    if kind == "filter":
        op, value = str(spec.get("operator") or "eq"), spec.get("value")
        operators = {
            "eq": work[col] == value, "ne": work[col] != value,
            "gt": work[col] > value, "gte": work[col] >= value,
            "lt": work[col] < value, "lte": work[col] <= value,
        }
        mask = operators.get(op)
        if mask is None:
            return work, {"type": kind, "status": "skipped", "reason": "invalid_operator"}
        before = len(work)
        return work.loc[mask.fillna(False)].copy(), {
            "type": kind, "column": col, "operator": op, "status": "applied",
            "rows_removed": before - int(mask.fillna(False).sum()),
        }
    if kind == "dax_calculated":
        from app.services.dax_engine import DaxError, parse_dax_expression, compile_dax_expression
        from app.services.dataset_engine import DatasetHandle

        target = str(spec.get("name") or "").strip()
        expression = str(spec.get("expression") or "")
        if not target or not SAFE_COLUMN_RE.match(target) or target in work.columns:
            return work, {"type": kind, "status": "skipped", "reason": "invalid_target"}
        try:
            compiled = compile_dax_expression(
                parse_dax_expression(expression), columns=work.columns,
                mode="calculated_column",
            )
            handle = DatasetHandle.from_dataframe(work)
            target_sql = '"' + target.replace('"', '""') + '"'
            work = handle.execute_select(
                f"SELECT *, {compiled} AS {target_sql} FROM df",
                max_rows=max(1, len(work)),
            )
        except (DaxError, ValueError, TypeError) as exc:
            return work, {"type": kind, "status": "skipped", "reason": str(exc)[:200]}
        return work, {"type": kind, "name": target, "formula_hash": spec.get("formula_hash"), "status": "applied"}
    # Derived columns use one safe arithmetic operation over existing columns/constants.
    target = str(spec.get("name") or "").strip()
    left, right = str(spec.get("left") or ""), spec.get("right")
    op = str(spec.get("operator") or "")
    if not target or not SAFE_COLUMN_RE.match(target) or target in work.columns or left not in work.columns:
        return work, {"type": kind, "status": "skipped", "reason": "invalid_expression"}
    lhs = pd.to_numeric(work[left], errors="coerce")
    rhs = pd.to_numeric(work[str(right)], errors="coerce") if str(right) in work.columns else float(right)
    operations = {"+": lhs + rhs, "-": lhs - rhs, "*": lhs * rhs}
    if op == "/":
        operations["/"] = lhs / pd.Series(rhs, index=work.index).replace(0, np.nan) if not isinstance(rhs, pd.Series) else lhs / rhs.replace(0, np.nan)
    if op not in operations:
        return work, {"type": kind, "status": "skipped", "reason": "invalid_operator"}
    work[target] = operations[op]
    return work, {"type": kind, "name": target, "status": "applied"}


def _contract_quality_alerts_dataframe(
    work: pd.DataFrame,
    contract: Dict[str, Any],
) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    for column, spec in (contract.get("column_contracts") or {}).items():
        if column not in work.columns:
            alerts.append({
                "column": column,
                "type": "contract_column_missing",
                "severity": "critical" if spec.get("required") else "warning",
            })
            continue
        if spec.get("required"):
            missing = int(work[column].isna().sum())
            if missing:
                alerts.append({
                    "column": column,
                    "type": "required_null",
                    "actual": missing,
                    "severity": "critical",
                })
        if spec.get("unique"):
            duplicates = int(work[column].duplicated(keep=False).sum())
            if duplicates:
                alerts.append({
                    "column": column,
                    "type": "uniqueness",
                    "actual": duplicates,
                    "severity": "warning",
                })
        allowed = spec.get("allowed_values") or []
        if allowed:
            invalid = int(
                (~work[column].isna() & ~work[column].astype(str).isin(allowed)).sum()
            )
            if invalid:
                alerts.append({
                    "column": column,
                    "type": "accepted_values",
                    "actual": invalid,
                    "severity": "warning",
                })
    keys = [key for key in contract.get("primary_keys") or [] if key in work.columns]
    if keys:
        null_keys = int(work[keys].isna().any(axis=1).sum())
        duplicate_keys = int(work.duplicated(subset=keys, keep=False).sum())
        if null_keys:
            alerts.append({
                "column": ",".join(keys),
                "type": "primary_key_null",
                "actual": null_keys,
                "severity": "critical",
            })
        if duplicate_keys:
            alerts.append({
                "column": ",".join(keys),
                "type": "primary_key_duplicate",
                "actual": duplicate_keys,
                "severity": "critical",
            })
    return alerts


def apply_recipe_dataframe(
    df: pd.DataFrame,
    recipe: Optional[Dict[str, Any]],
    mapping: Optional[Dict[str, str]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    normalized = normalize_recipe(recipe)
    started = datetime.now(timezone.utc).isoformat()
    if not normalized["apply"]:
        return df.copy(), {"version": RECIPE_VERSION, "applied": False, "recipe_hash": recipe_hash(normalized)}
    work = df.copy()
    audit: Dict[str, Any] = {
        "version": RECIPE_VERSION, "applied": True, "recipe_hash": recipe_hash(normalized),
        "started_at": started, "rows_before": len(work), "columns_before": list(map(str, work.columns)),
        "imputations": [], "outliers": [], "transformations": [], "quality_alerts": [],
    }
    for spec in normalized["imputations"]:
        col = str(spec.get("column") or "")
        item = dict(spec)
        if col in work.columns:
            item["_missing_mask"] = work[col].isna().copy()
        outcome = _apply_imputation(work, item, mapping)
        if outcome:
            audit["imputations"].append(outcome)
    detected = {item["column"]: item for item in detect_outliers(work, mapping=mapping)}
    for spec in normalized["outliers"]:
        col, action = str(spec.get("column") or ""), str(spec.get("action") or "flag")
        detail = detected.get(col)
        if not detail or action not in OUTLIER_ACTIONS:
            continue
        values = pd.to_numeric(work[col], errors="coerce")
        mask = (values < detail["lower_bound"]) | (values > detail["upper_bound"])
        if action == "flag":
            work[f"{col}__outlier"] = mask
        elif action in {"exclude", "delete"}:
            work = work.loc[~mask].copy()
        elif action == "winsorize":
            work[col] = values.clip(detail["lower_bound"], detail["upper_bound"])
        audit["outliers"].append({**detail, "action": action, "affected": int(mask.sum())})
    for spec in normalized["invalid_dates"]:
        col, action = str(spec.get("column") or ""), str(spec.get("action") or "flag")
        if col not in work.columns or action not in {"flag", "exclude", "keep_missing"}:
            continue
        mask = work[col].isna()
        if action == "flag":
            work[f"{col}__invalid_or_missing"] = mask
        elif action == "exclude":
            work = work.loc[~mask].copy()
        audit["transformations"].append({
            "type": "invalid_date_resolution", "column": col,
            "action": action, "affected": int(mask.sum()), "status": "applied",
        })
    for spec in normalized["transformations"]:
        work, outcome = _apply_transform(work, spec)
        audit["transformations"].append(outcome)
    for rule in normalized["quality_rules"]:
        col = str(rule.get("column") or "")
        if col not in work.columns:
            continue
        max_missing = float(rule.get("max_missing_rate", 1))
        rate = float(work[col].isna().mean()) if len(work) else 0
        if rate > max_missing:
            audit["quality_alerts"].append({
                "column": col, "type": "missing_rate", "actual": round(rate, 4),
                "threshold": max_missing, "severity": rule.get("severity", "warning"),
            })
    audit["quality_alerts"].extend(
        _contract_quality_alerts_dataframe(work, normalized["data_contract"])
    )
    audit.update({
        "rows_after": len(work), "columns_after": list(map(str, work.columns)),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })
    return work, to_json_safe(audit)


def apply_recipe_duckdb(
    handle: Any,
    recipe: Optional[Dict[str, Any]],
    mapping: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Apply the same explicit recipe directly to a DuckDB-backed full dataset."""
    from app.services.dataset_engine import TABLE_NAME, _quote_ident

    normalized = normalize_recipe(recipe)
    audit: Dict[str, Any] = {
        "version": RECIPE_VERSION, "applied": bool(normalized["apply"]),
        "recipe_hash": recipe_hash(normalized), "engine": "duckdb",
        "rows_before": handle.row_count(), "imputations": [], "outliers": [],
        "transformations": [], "quality_alerts": [],
    }
    if not normalized["apply"]:
        return audit
    con = handle._con

    def columns() -> List[str]:
        return [r[0] for r in con.execute(f"DESCRIBE {TABLE_NAME}").fetchall()]

    def replace_from(select_sql: str, params: Optional[List[Any]] = None) -> None:
        con.execute("DROP TABLE IF EXISTS __etl_next")
        con.execute(f"CREATE TABLE __etl_next AS {select_sql}", params or [])
        raw = handle._ensure_raw_table()
        con.execute(f"DROP VIEW IF EXISTS {TABLE_NAME}")
        con.execute(f"DROP TABLE IF EXISTS {raw}")
        con.execute(f"ALTER TABLE __etl_next RENAME TO {raw}")
        con.execute(f"CREATE VIEW {TABLE_NAME} AS SELECT * FROM {raw}")
        handle._raw_table = raw

    for spec in normalized["imputations"]:
        col, method = str(spec.get("column") or ""), str(spec.get("method") or "")
        if col not in columns() or method not in IMPUTE_METHODS:
            continue
        if _role(mapping, col) in CRITICAL_ROLES and not bool(spec.get("confirmed")):
            audit["imputations"].append({"column": col, "method": method, "changed": 0, "skipped": "confirmation_required"})
            continue
        q = _quote_ident(col)
        missing = int(con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE {q} IS NULL").fetchone()[0])
        if missing:
            raw = handle._ensure_raw_table()
            flag = _quote_ident(f"{col}__imputed")
            try:
                con.execute(f"ALTER TABLE {raw} ADD COLUMN {flag} BOOLEAN DEFAULT FALSE")
                con.execute(f"UPDATE {raw} SET {flag} = ({q} IS NULL)")
                con.execute(f"DROP VIEW IF EXISTS {TABLE_NAME}")
                con.execute(f"CREATE VIEW {TABLE_NAME} AS SELECT * FROM {raw}")
            except Exception:
                pass
        if method in {"median", "mean", "mode"}:
            aggregate = {
                "median": f"MEDIAN({q})", "mean": f"AVG({q})",
                "mode": f"MODE({q})",
            }[method]
            value = con.execute(f"SELECT {aggregate} FROM {TABLE_NAME}").fetchone()[0]
            con.execute(f"UPDATE {handle._ensure_raw_table()} SET {q} = ? WHERE {q} IS NULL", [value])
        elif method == "constant":
            con.execute(
                f"UPDATE {handle._ensure_raw_table()} SET {q} = ? WHERE {q} IS NULL",
                [spec.get("value", "Unknown")],
            )
        else:
            direction = "ORDER BY __etl_order DESC" if method == "backward_fill" else "ORDER BY __etl_order"
            parts = []
            for current in columns():
                cq = _quote_ident(current)
                parts.append(
                    f"LAST_VALUE({cq} IGNORE NULLS) OVER ({direction}) AS {cq}"
                    if current == col else cq
                )
            replace_from(
                f"SELECT {', '.join(parts)} FROM "
                f"(SELECT *, ROW_NUMBER() OVER () __etl_order FROM {TABLE_NAME}) src"
            )
        audit["imputations"].append({"column": col, "method": method, "changed": missing})

    for spec in normalized["outliers"]:
        col, action = str(spec.get("column") or ""), str(spec.get("action") or "flag")
        if col not in columns() or action not in OUTLIER_ACTIONS:
            continue
        q = _quote_ident(col)
        q1, q3 = con.execute(
            f"SELECT QUANTILE_CONT({q}, .25), QUANTILE_CONT({q}, .75) FROM {TABLE_NAME}"
        ).fetchone()
        if q1 is None or q3 is None:
            continue
        lower, upper = float(q1) - 1.5 * float(q3 - q1), float(q3) + 1.5 * float(q3 - q1)
        condition = f"({q} < {lower} OR {q} > {upper})"
        affected = int(con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE {condition}").fetchone()[0])
        raw = handle._ensure_raw_table()
        if action == "flag":
            flag = _quote_ident(f"{col}__outlier")
            con.execute(f"ALTER TABLE {raw} ADD COLUMN {flag} BOOLEAN DEFAULT FALSE")
            con.execute(f"UPDATE {raw} SET {flag} = {condition}")
            con.execute(f"DROP VIEW IF EXISTS {TABLE_NAME}")
            con.execute(f"CREATE VIEW {TABLE_NAME} AS SELECT * FROM {raw}")
        elif action in {"exclude", "delete"}:
            replace_from(f"SELECT * FROM {TABLE_NAME} WHERE NOT {condition}")
        elif action == "winsorize":
            con.execute(
                f"UPDATE {raw} SET {q} = CASE WHEN {q} < ? THEN ? WHEN {q} > ? THEN ? ELSE {q} END",
                [lower, lower, upper, upper],
            )
        audit["outliers"].append({
            "column": col, "method": "iqr", "lower_bound": lower,
            "upper_bound": upper, "action": action, "affected": affected,
        })
    for spec in normalized["invalid_dates"]:
        col, action = str(spec.get("column") or ""), str(spec.get("action") or "flag")
        if col not in columns() or action not in {"flag", "exclude", "keep_missing"}:
            continue
        q = _quote_ident(col)
        affected = int(con.execute(
            f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE {q} IS NULL"
        ).fetchone()[0])
        if action == "flag":
            raw = handle._ensure_raw_table()
            flag = _quote_ident(f"{col}__invalid_or_missing")
            con.execute(f"ALTER TABLE {raw} ADD COLUMN {flag} BOOLEAN DEFAULT FALSE")
            con.execute(f"UPDATE {raw} SET {flag} = ({q} IS NULL)")
            con.execute(f"DROP VIEW IF EXISTS {TABLE_NAME}")
            con.execute(f"CREATE VIEW {TABLE_NAME} AS SELECT * FROM {raw}")
        elif action == "exclude":
            replace_from(f"SELECT * FROM {TABLE_NAME} WHERE {q} IS NOT NULL")
        audit["transformations"].append({
            "type": "invalid_date_resolution", "column": col,
            "action": action, "affected": affected, "status": "applied",
        })

    for spec in normalized["transformations"]:
        kind, col = str(spec.get("type") or ""), str(spec.get("column") or "")
        outcome: Dict[str, Any] = {"type": kind, "status": "skipped"}
        if kind == "rename" and col in columns():
            target = str(spec.get("to") or "")
            if target and SAFE_COLUMN_RE.match(target) and target not in columns():
                con.execute(f"ALTER TABLE {handle._ensure_raw_table()} RENAME COLUMN {_quote_ident(col)} TO {_quote_ident(target)}")
                outcome = {"type": kind, "column": col, "to": target, "status": "applied"}
        elif kind == "type_cast" and col in columns():
            dtype = {"numeric": "DOUBLE", "date": "TIMESTAMP", "text": "VARCHAR"}.get(str(spec.get("to")))
            if dtype:
                parts = [
                    f"TRY_CAST({_quote_ident(c)} AS {dtype}) AS {_quote_ident(c)}"
                    if c == col else _quote_ident(c) for c in columns()
                ]
                replace_from(f"SELECT {', '.join(parts)} FROM {TABLE_NAME}")
                outcome = {"type": kind, "column": col, "to": spec.get("to"), "status": "applied"}
        elif kind == "filter" and col in columns():
            operator = {"eq": "=", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}.get(str(spec.get("operator")))
            if operator:
                before = handle.row_count()
                replace_from(f"SELECT * FROM {TABLE_NAME} WHERE {_quote_ident(col)} {operator} ?", [spec.get("value")])
                outcome = {"type": kind, "column": col, "status": "applied", "rows_removed": before - int(con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0])}
        elif kind == "derived":
            target, left, right = str(spec.get("name") or ""), str(spec.get("left") or ""), spec.get("right")
            op = str(spec.get("operator") or "")
            if target and SAFE_COLUMN_RE.match(target) and left in columns() and op in {"+", "-", "*", "/"}:
                rhs = _quote_ident(str(right)) if str(right) in columns() else str(float(right))
                expr = f"{_quote_ident(left)} {op} NULLIF({rhs}, 0)" if op == "/" else f"{_quote_ident(left)} {op} {rhs}"
                replace_from(f"SELECT *, {expr} AS {_quote_ident(target)} FROM {TABLE_NAME}")
                outcome = {"type": kind, "name": target, "status": "applied"}
        elif kind == "dax_calculated":
            from app.services.dax_engine import DaxError, parse_dax_expression, compile_dax_expression

            target = str(spec.get("name") or "").strip()
            expression = str(spec.get("expression") or "")
            if target and SAFE_COLUMN_RE.match(target) and target not in columns():
                try:
                    compiled = compile_dax_expression(
                        parse_dax_expression(expression), columns=columns(),
                        mode="calculated_column",
                    )
                    replace_from(
                        f"SELECT *, {compiled} AS {_quote_ident(target)} FROM {TABLE_NAME}"
                    )
                    outcome = {"type": kind, "name": target, "formula_hash": spec.get("formula_hash"), "status": "applied"}
                except DaxError as exc:
                    outcome = {"type": kind, "status": "skipped", "reason": str(exc)[:200]}
        audit["transformations"].append(outcome)

    for rule in normalized["quality_rules"]:
        col = str(rule.get("column") or "")
        if col not in columns():
            continue
        missing, total = con.execute(
            f"SELECT COUNT(*) FILTER (WHERE {_quote_ident(col)} IS NULL), COUNT(*) FROM {TABLE_NAME}"
        ).fetchone()
        rate = float(missing or 0) / max(int(total or 0), 1)
        threshold = float(rule.get("max_missing_rate", 1))
        if rate > threshold:
            audit["quality_alerts"].append({"column": col, "type": "missing_rate", "actual": round(rate, 4), "threshold": threshold, "severity": rule.get("severity", "warning")})
    for column, spec in (normalized["data_contract"].get("column_contracts") or {}).items():
        if column not in columns():
            audit["quality_alerts"].append({
                "column": column,
                "type": "contract_column_missing",
                "severity": "critical" if spec.get("required") else "warning",
            })
            continue
        q = _quote_ident(column)
        if spec.get("required"):
            missing = int(con.execute(
                f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE {q} IS NULL"
            ).fetchone()[0])
            if missing:
                audit["quality_alerts"].append({
                    "column": column, "type": "required_null",
                    "actual": missing, "severity": "critical",
                })
        if spec.get("unique"):
            duplicates = int(con.execute(
                f"SELECT COALESCE(SUM(n), 0) FROM "
                f"(SELECT COUNT(*) n FROM {TABLE_NAME} GROUP BY {q} HAVING COUNT(*) > 1)"
            ).fetchone()[0])
            if duplicates:
                audit["quality_alerts"].append({
                    "column": column, "type": "uniqueness",
                    "actual": duplicates, "severity": "warning",
                })
        allowed = spec.get("allowed_values") or []
        if allowed:
            placeholders = ", ".join("?" for _ in allowed)
            invalid = int(con.execute(
                f"SELECT COUNT(*) FROM {TABLE_NAME} "
                f"WHERE {q} IS NOT NULL AND CAST({q} AS VARCHAR) NOT IN ({placeholders})",
                allowed,
            ).fetchone()[0])
            if invalid:
                audit["quality_alerts"].append({
                    "column": column, "type": "accepted_values",
                    "actual": invalid, "severity": "warning",
                })
    keys = [
        key for key in normalized["data_contract"].get("primary_keys") or []
        if key in columns()
    ]
    if keys:
        quoted_keys = [_quote_ident(key) for key in keys]
        null_condition = " OR ".join(f"{key} IS NULL" for key in quoted_keys)
        null_keys = int(con.execute(
            f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE {null_condition}"
        ).fetchone()[0])
        group_by = ", ".join(quoted_keys)
        duplicate_keys = int(con.execute(
            f"SELECT COALESCE(SUM(n), 0) FROM "
            f"(SELECT COUNT(*) n FROM {TABLE_NAME} GROUP BY {group_by} HAVING COUNT(*) > 1)"
        ).fetchone()[0])
        if null_keys:
            audit["quality_alerts"].append({
                "column": ",".join(keys), "type": "primary_key_null",
                "actual": null_keys, "severity": "critical",
            })
        if duplicate_keys:
            audit["quality_alerts"].append({
                "column": ",".join(keys), "type": "primary_key_duplicate",
                "actual": duplicate_keys, "severity": "critical",
            })
    handle._cached_row_count = int(con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0])
    handle.invalidate_summarize_cache()
    audit["rows_after"] = handle._cached_row_count
    audit["columns_after"] = columns()
    return to_json_safe(audit)


def build_cleaning_preview(
    before: pd.DataFrame,
    after: pd.DataFrame,
    report: Dict[str, Any],
    mapping: Optional[Dict[str, str]] = None,
    *,
    sampled: bool = False,
    total_rows: Optional[int] = None,
) -> Dict[str, Any]:
    return to_json_safe({
        "sampled": sampled,
        "sample_rows": len(before),
        "total_rows": total_rows if total_rows is not None else len(before),
        "rows_before": len(before),
        "rows_after": len(after),
        "columns_before": list(map(str, before.columns)),
        "columns_after": list(map(str, after.columns)),
        "before": before.head(10).where(pd.notna(before.head(10)), None).to_dict("records"),
        "after": after.head(10).where(pd.notna(after.head(10)), None).to_dict("records"),
        "cleaning_report": report,
        "missing_recommendations": missing_value_recommendations(before, mapping),
        "outlier_candidates": detect_outliers(before, mapping=mapping),
    })
