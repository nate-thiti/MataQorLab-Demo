"""Conservative deterministic SQL templates used before LLM SQL generation."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.services.dataset_engine import DatasetHandle


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _mentioned_column(question: str, columns: list[str]) -> Optional[str]:
    lower = question.lower()
    matches = [col for col in columns if str(col).lower() in lower]
    return max(matches, key=len) if matches else None


def _resolve_columns(
    handle: DatasetHandle,
    question: str,
    column_mapping: Optional[Dict[str, str]] = None,
) -> Dict[str, Optional[str]]:
    text = (question or "").lower()
    roles = handle.infer_roles_from_sample(column_mapping or {})
    columns = handle.column_names()
    mentioned = _mentioned_column(text, columns)
    metric = mentioned or next(
        (roles.get(role) for role in ("sales", "cost", "quantity", "output", "salary") if roles.get(role)),
        None,
    )
    dimension = next(
        (
            roles.get(role)
            for role in ("product", "category", "branch", "country", "department", "supplier")
            if roles.get(role)
        ),
        None,
    )
    date_col = roles.get("date") or roles.get("timestamp")
    return {
        "text": text,
        "roles": roles,
        "metric": metric,
        "dimension": dimension,
        "date_col": date_col,
    }


def infer_question_sql_contract(
    handle: DatasetHandle,
    question: str,
    column_mapping: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """Infer expected aggregate semantics even when no deterministic template is used."""
    template = match_sql_template(handle, question, column_mapping)
    if template:
        return dict(template.get("contract") or {})
    ctx = _resolve_columns(handle, question, column_mapping)
    text = ctx["text"]
    metric = ctx["metric"]
    dimension = ctx["dimension"]
    date_col = ctx["date_col"]
    if re.search(r"\b(count|how many|number of)\b|จำนวน|กี่", text):
        return {"operation": "count", "columns": []}
    if not metric:
        return None
    if re.search(r"\b(average|avg|mean)\b|เฉลี่ย", text):
        return {"operation": "average", "columns": [metric]}
    if re.search(r"\b(total|sum)\b|รวม|ทั้งหมด", text) and not re.search(
        r"\b(by|per|top)\b|ตาม|สูงสุด", text
    ):
        return {"operation": "sum", "columns": [metric]}
    if dimension and re.search(r"\b(top|highest|largest|best)\b|สูงสุด|อันดับ", text):
        return {"operation": "top", "columns": [dimension, metric]}
    if date_col and re.search(r"\b(trend|monthly|over time|mom)\b|แนวโน้ม|รายเดือน", text):
        return {"operation": "trend", "columns": [date_col, metric]}
    if re.search(r"\b(group|breakdown|by)\b|ตาม|แยกตาม", text) and dimension:
        return {"operation": "group", "columns": [dimension, metric]}
    return {"operation": "aggregate", "columns": [metric]}


def match_sql_template(
    handle: DatasetHandle,
    question: str,
    column_mapping: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """Return SQL only when intent and semantic columns are unambiguous."""
    ctx = _resolve_columns(handle, question, column_mapping)
    text = ctx["text"]
    metric = ctx["metric"]
    dimension = ctx["dimension"]
    date_col = ctx["date_col"]

    if re.search(r"\b(count|how many|number of)\b|จำนวน|กี่", text):
        return {
            "template_id": "count_rows",
            "sql": "SELECT COUNT(*) AS row_count FROM df",
            "contract": {"operation": "count", "columns": []},
        }
    if not metric:
        return None
    qm = _q(metric)
    if re.search(r"\b(average|avg|mean)\b|เฉลี่ย", text):
        alias = _q(f"average_{metric}")
        return {
            "template_id": "average_metric",
            "sql": f"SELECT AVG(TRY_CAST({qm} AS DOUBLE)) AS {alias} FROM df",
            "contract": {"operation": "average", "columns": [metric]},
        }
    if re.search(r"\b(total|sum)\b|รวม|ทั้งหมด", text) and not re.search(r"\b(by|per|top)\b|ตาม|สูงสุด", text):
        alias = _q(f"total_{metric}")
        return {
            "template_id": "total_metric",
            "sql": f"SELECT SUM(TRY_CAST({qm} AS DOUBLE)) AS {alias} FROM df",
            "contract": {"operation": "sum", "columns": [metric]},
        }
    if dimension and re.search(r"\b(top|highest|largest|best)\b|สูงสุด|อันดับ", text):
        qd = _q(dimension)
        alias = _q(f"total_{metric}")
        return {
            "template_id": "top_dimension",
            "sql": (
                f"SELECT {qd} AS {qd}, SUM(TRY_CAST({qm} AS DOUBLE)) AS {alias} "
                f"FROM df GROUP BY 1 ORDER BY {alias} DESC LIMIT 10"
            ),
            "contract": {"operation": "top", "columns": [dimension, metric]},
        }
    if date_col and re.search(r"\b(trend|monthly|over time|mom)\b|แนวโน้ม|รายเดือน", text):
        qd = _q(date_col)
        alias = _q(f"total_{metric}")
        return {
            "template_id": "monthly_trend",
            "sql": (
                f"SELECT DATE_TRUNC('month', TRY_CAST({qd} AS TIMESTAMP)) AS period, "
                f"SUM(TRY_CAST({qm} AS DOUBLE)) AS {alias} FROM df "
                "WHERE TRY_CAST(" + qd + " AS TIMESTAMP) IS NOT NULL "
                "GROUP BY 1 ORDER BY 1 LIMIT 100"
            ),
            "contract": {"operation": "trend", "columns": [date_col, metric]},
        }
    if re.search(
        r"\b(visualization|dashboard|report|chart|graph)\b|รายงาน|กราฟ|แดชบอร์ด",
        text,
    ):
        if dimension:
            qd = _q(dimension)
            alias = _q(f"total_{metric}")
            return {
                "template_id": "visualization_overview",
                "sql": (
                    f"SELECT {qd} AS {qd}, SUM(TRY_CAST({qm} AS DOUBLE)) AS {alias} "
                    f"FROM df GROUP BY 1 ORDER BY {alias} DESC LIMIT 20"
                ),
                "contract": {"operation": "group", "columns": [dimension, metric]},
            }
        if date_col:
            qd = _q(date_col)
            alias = _q(f"total_{metric}")
            return {
                "template_id": "visualization_trend",
                "sql": (
                    f"SELECT DATE_TRUNC('month', TRY_CAST({qd} AS TIMESTAMP)) AS period, "
                    f"SUM(TRY_CAST({qm} AS DOUBLE)) AS {alias} FROM df "
                    f"WHERE TRY_CAST({qd} AS TIMESTAMP) IS NOT NULL "
                    "GROUP BY 1 ORDER BY 1 LIMIT 100"
                ),
                "contract": {"operation": "trend", "columns": [date_col, metric]},
            }
    return None


def validate_sql_semantics(sql: str, contract: Optional[Dict[str, Any]]) -> list[str]:
    if not contract:
        return []
    lower = (sql or "").lower()
    warnings = []
    operation = contract.get("operation")
    required_function = {
        "sum": "sum(",
        "average": "avg(",
        "count": "count(",
        "top": "sum(",
        "trend": "date_trunc(",
        "group": "group by",
    }.get(operation)
    if required_function and required_function not in lower:
        warnings.append(f"Expected {operation} semantics were not found in SQL.")
    for col in contract.get("columns") or []:
        if str(col).lower() not in lower:
            warnings.append(f"Expected column {col} was not found in SQL.")
    return warnings


def validate_llm_sql(
    sql: str,
    question: str,
    handle: DatasetHandle,
    column_mapping: Optional[Dict[str, str]] = None,
) -> Tuple[bool, List[str]]:
    """Reject LLM SQL that is unsafe or clearly misaligned with the question."""
    errors: List[str] = []
    lower = (sql or "").lower().strip()
    if not lower:
        return False, ["Empty SQL query."]
    if not (lower.startswith("select") or lower.startswith("with")):
        errors.append("Query must start with SELECT or WITH.")
    if re.search(r"\b(insert|update|delete|drop|create|alter|truncate|attach|copy|export|import)\b", lower):
        errors.append("Only read-only SELECT analytics are allowed.")
    if re.search(r"select\s+\*\s+from\s+df\b", lower) and "group by" not in lower:
        errors.append("SELECT * without GROUP BY is not allowed on the full dataset.")
    if "limit" not in lower and "group by" not in lower and "count(" not in lower:
        errors.append("Non-aggregate queries must include GROUP BY or LIMIT.")

    contract = infer_question_sql_contract(handle, question, column_mapping)
    if contract:
        errors.extend(validate_sql_semantics(sql, contract))

    ctx = _resolve_columns(handle, question, column_mapping)
    metric = ctx.get("metric")
    dimension = ctx.get("dimension")
    text = ctx.get("text") or ""
    if metric and metric.lower() not in lower and contract and contract.get("operation") != "count":
        errors.append(f"Expected metric column {metric} is missing from SQL.")
    if dimension and re.search(r"\b(by|per|top|group)\b|ตาม|สูงสุด|แยก", text):
        if dimension.lower() not in lower:
            errors.append(f"Expected breakdown column {dimension} is missing from SQL.")
    if re.search(r"\bwhere\b", text) or re.search(r"เฉพาะ|only|just", text):
        literal = _mentioned_literal_filter(question, handle.column_names())
        if literal and literal.lower() not in lower:
            errors.append(f"Expected filter for '{literal}' is missing from SQL.")

    return len(errors) == 0, errors


def _mentioned_literal_filter(question: str, columns: list[str]) -> Optional[str]:
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'|“([^”]+)”|‘([^’]+)’', question or "")
    for groups in quoted:
        for value in groups:
            if value:
                return value.strip()
    lower = (question or "").lower()
    for col in columns:
        pattern = re.compile(
            rf"{re.escape(str(col).lower())}\s*(?:=|is|:)?\s*([a-z0-9\u0e00-\u0e7f][\w\u0e00-\u0e7f]*)",
            re.IGNORECASE,
        )
        match = pattern.search(lower)
        if match:
            return match.group(1)
    return None
