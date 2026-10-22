"""
Question-aware analytics: generate and execute DuckDB SQL tailored to the user's question.
All datasets run through DuckDB SQL (no Pandas exec sandbox).
LLM-facing output is aggregate/summary only — never raw row dumps.
"""
import re
from typing import Any, Callable, Dict, List, Optional, Awaitable, Union

import pandas as pd

from app.services.dataset_engine import TABLE_NAME, DatasetHandle, as_handle
from app.services.sql_templates import (
    infer_question_sql_contract,
    match_sql_template,
    validate_llm_sql,
    validate_sql_semantics,
)
from app.services.structured_findings import finding_from_query_result
from app.services.web_search import dedupe_web_sources

MAX_RESULT_ROWS = 100
MAX_AGGREGATE_GROUPS = 25
MAX_RESULT_CHARS = 4000
MAX_CODE_GEN_TOKENS = 500


def _truncate_restarted_query(sql: str) -> str:
    """Drop a second top-level query accidentally emitted in one SQL block."""
    lines = (sql or "").splitlines()
    depth = 0
    top_level_selects = 0
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            output.append(line)
            continue
        keyword = re.match(r"^(select|with)\b", stripped, re.IGNORECASE)
        if depth == 0 and keyword:
            word = keyword.group(1).lower()
            if word == "select":
                top_level_selects += 1
                if top_level_selects > 1:
                    break
        output.append(line)
        # Dashboard/analytics SQL does not permit string-built DDL. This
        # lightweight balance is sufficient to distinguish CTE subqueries.
        code = re.sub(r"'(?:''|[^'])*'", "''", line.split("--", 1)[0])
        depth = max(0, depth + code.count("(") - code.count(")"))
    return "\n".join(output).strip()


def extract_sql_code(text: str) -> str:
    text = (text or "").strip()
    match = re.search(r"```sql\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match:
        text = match.group(1).strip()
    else:
        match = re.search(r"```\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1).strip()

    cleaned = text.strip()
    if not cleaned:
        return ""

    start_match = re.search(r"\b(with|select)\b", cleaned, re.IGNORECASE)
    if start_match:
        cleaned = cleaned[start_match.start():].strip()

    statement = cleaned.split(";", 1)[0].strip()
    if statement:
        return _truncate_restarted_query(statement)
    return cleaned.rstrip(";").strip()


def format_aggregate_result(
    result: Any,
    *,
    max_groups: int = MAX_AGGREGATE_GROUPS,
    max_chars: int = MAX_RESULT_CHARS,
) -> str:
    """Format SQL output as compact aggregate summary for LLM context."""
    if isinstance(result, pd.Series):
        result = result.to_frame(name="value")
    if not isinstance(result, pd.DataFrame):
        out = str(result)
        return out[:max_chars] if len(out) > max_chars else out

    if result.empty:
        return "No matching rows."

    cols = list(result.columns)
    n = len(result)

    if n == 1 and len(cols) == 1:
        return f"- {cols[0]}: {result.iloc[0, 0]}"

    if n == 1:
        parts = [f"- {col}: {result.iloc[0][col]}" for col in cols]
        return "\n".join(parts)

    lines = [f"Aggregate summary ({n} groups, full dataset scanned):"]
    display_cols = cols[:6]
    for _, row in result.head(max_groups).iterrows():
        if len(display_cols) >= 2:
            label = str(row[display_cols[0]])
            metrics = ", ".join(f"{c}={row[c]}" for c in display_cols[1:])
            lines.append(f"- {label}: {metrics}")
        else:
            lines.append(f"- {row[display_cols[0]]}")

    if n > max_groups:
        lines.append(f"[... {n - max_groups} additional groups omitted from LLM context]")
    out = "\n".join(lines)
    if len(out) > max_chars:
        out = out[: max_chars - 40] + "\n[Truncated for context limits]"
    return out


def extract_chart_hint(result: Any) -> Optional[Dict[str, Any]]:
    if isinstance(result, pd.Series):
        if len(result) < 2 or len(result) > 30:
            return None
        numeric = pd.to_numeric(result, errors="coerce")
        if not numeric.notna().any():
            return None
        data = []
        for name, val in result.head(30).items():
            num = numeric.loc[name]
            if pd.isna(num):
                continue
            data.append({"name": str(name), "value": float(num)})
        if len(data) < 2:
            return None
        return {
            "chart_type": "bar",
            "config": {"title": "Query result", "xAxis": "name", "series": ["value"]},
            "data": data,
        }

    if not isinstance(result, pd.DataFrame):
        return None
    if len(result) < 2 or len(result) > 30 or len(result.columns) < 2:
        return None

    cols = list(result.columns)
    name_col = cols[0]
    numeric_cols = [
        c for c in cols[1:]
        if pd.to_numeric(result[c], errors="coerce").notna().sum() >= max(2, len(result) // 2)
    ]
    if not numeric_cols:
        return None

    val_col = numeric_cols[0]
    data = []
    for _, row in result.head(30).iterrows():
        num = pd.to_numeric(row[val_col], errors="coerce")
        if pd.isna(num):
            continue
        data.append({"name": str(row[name_col]), val_col: float(num)})
    if len(data) < 2:
        return None

    chart_type = "bar" if len(data) <= 15 else "line"
    return {
        "chart_type": chart_type,
        "config": {"title": "Analysis aggregate", "xAxis": "name", "series": [val_col]},
        "data": data,
    }


def _build_sql_codegen_prompt(
    handle: DatasetHandle,
    user_question: str,
    column_mapping: Optional[Dict[str, str]] = None,
    prior_error: Optional[str] = None,
    prior_sql: Optional[str] = None,
) -> str:
    profile = handle.profile_columns()
    cols = ", ".join(handle.column_names())
    mapping_note = ""
    if column_mapping:
        mapping_note = f"\nSemantic column mapping: {column_mapping}\n"

    retry_note = ""
    if prior_error and prior_sql:
        retry_note = (
            f"\nYour previous SQL failed:\n```sql\n{prior_sql}\n```\n"
            f"Error: {prior_error}\nFix the query and try again.\n"
        )

    return (
        f"You are a DuckDB SQL analyst. Table `{TABLE_NAME}` "
        f"has {handle.row_count():,} rows.\n"
        f"Columns: {cols}\n"
        f"{mapping_note}\n"
        f"Column Profile:\n{profile}\n\n"
        f"User question: \"{user_question}\"\n"
        f"{retry_note}\n"
        "Write a single DuckDB SQL SELECT query against table `df` that answers the question.\n"
        "Rules:\n"
        "1. Respond ONLY with SQL inside a ```sql ... ``` block.\n"
        "2. Only SELECT — no INSERT/UPDATE/DELETE/DDL.\n"
        "3. Prefer GROUP BY and aggregates (SUM, COUNT, AVG) — avoid SELECT * on raw rows.\n"
        "4. LIMIT grouped results to 100 rows unless user explicitly needs row-level export.\n"
        "5. Use DuckDB functions (date_trunc, try_cast, etc.) as needed.\n"
        "6. Quote column names with double quotes if they contain spaces or special characters.\n"
    )


async def _run_duckdb_analytics(
    handle: DatasetHandle,
    user_question: str,
    model: str,
    chat_completion_fn: Callable[..., Awaitable[Any]],
    column_mapping: Optional[Dict[str, str]] = None,
    max_llm_attempts: int = 2,
) -> Optional[Dict[str, Any]]:
    question = (user_question or "").strip()
    exec_handle = DatasetHandle.for_sql_execution(handle)
    prior_sql: Optional[str] = None
    prior_error: Optional[str] = None
    template = match_sql_template(exec_handle, question, column_mapping)
    if template:
        try:
            sql = template["sql"]
            result_df = exec_handle.execute_select(sql, max_rows=MAX_RESULT_ROWS)
            aggregate_summary = format_aggregate_result(result_df)
            chart_hint = extract_chart_hint(result_df)
            out = _success_result(
                question,
                exec_handle.row_count(),
                aggregate_summary,
                sql,
                1,
                "duckdb_template",
                chart_hint,
                result_row_count=len(result_df),
            )
            out["template_id"] = template["template_id"]
            out["semantic_contract"] = template["contract"]
            out["semantic_warnings"] = validate_sql_semantics(sql, template["contract"])
            out["structured_findings"] = finding_from_query_result(
                question,
                sql,
                result_df,
                rows_analyzed=exec_handle.row_count(),
                template_id=template["template_id"],
            )
            return out
        except Exception as exc:
            prior_error = str(exc)
            prior_sql = template["sql"]
            print(f"Deterministic SQL template failed, falling back to LLM SQL: {exc}")

    semantic_contract = infer_question_sql_contract(exec_handle, question, column_mapping)

    remaining_calls = getattr(chat_completion_fn, "remaining_calls", None)
    available_calls = (
        max(0, int(remaining_calls()))
        if callable(remaining_calls)
        else max_llm_attempts
    )
    attempt_limit = min(max(0, int(max_llm_attempts)), available_calls)
    for attempt in range(attempt_limit):
        prompt = _build_sql_codegen_prompt(exec_handle, question, column_mapping, prior_error, prior_sql)
        try:
            response = await chat_completion_fn(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=MAX_CODE_GEN_TOKENS,
            )
            sql = extract_sql_code(response.choices[0].message.content or "")
            prior_sql = sql
            valid, semantic_errors = validate_llm_sql(
                sql,
                question,
                exec_handle,
                column_mapping,
            )
            if not valid:
                prior_error = "Semantic validation failed:\n- " + "\n- ".join(semantic_errors)
                print(f"DuckDB analytics attempt {attempt + 1} rejected before execute: {prior_error}")
                continue
            result_df = exec_handle.execute_select(sql, max_rows=MAX_RESULT_ROWS)
            aggregate_summary = format_aggregate_result(result_df)
            chart_hint = extract_chart_hint(result_df)
            out = _success_result(
                question,
                exec_handle.row_count(),
                aggregate_summary,
                sql,
                attempt + 1,
                "duckdb",
                chart_hint,
                result_row_count=len(result_df),
            )
            out["semantic_contract"] = semantic_contract
            out["semantic_warnings"] = validate_sql_semantics(sql, semantic_contract)
            out["structured_findings"] = finding_from_query_result(
                question,
                sql,
                result_df,
                rows_analyzed=exec_handle.row_count(),
            )
            return out
        except Exception as e:
            prior_error = str(e)
            print(f"DuckDB analytics attempt {attempt + 1} failed: {e}")
    return _failure_result(
        question,
        exec_handle.row_count(),
        prior_error or "LLM call budget exhausted before SQL generation",
        prior_sql,
        "duckdb",
        attempts=attempt_limit,
    )


def _success_result(
    question: str,
    rows: int,
    aggregate_summary: str,
    code: str,
    attempts: int,
    engine: str,
    chart_hint: Optional[Dict[str, Any]] = None,
    result_row_count: int = 0,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "formatted": (
            f"Question: \"{question}\"\n"
            f"Rows analyzed: {rows:,}\n"
            f"Engine: {engine}\n"
            f"Aggregate result ({result_row_count} groups/values):\n{aggregate_summary}"
        ),
        "question": question,
        "rows_analyzed": rows,
        "code": code,
        "engine": engine,
        "success": True,
        "attempts": attempts,
        "aggregate_only": True,
    }
    if chart_hint:
        out["chart_hint"] = chart_hint
    return out


def _failure_result(
    question: str,
    rows: int,
    error: Optional[str],
    code: Optional[str],
    engine: str,
    *,
    attempts: int = 0,
) -> Dict[str, Any]:
    return {
        "formatted": (
            f"Question: \"{question}\"\n"
            f"Rows available: {rows:,}\n"
            f"Engine: {engine}\n"
            "Question-specific SQL analysis could not be completed automatically"
            f"{f': {error}' if error else '.'}"
        ),
        "question": question,
        "rows_analyzed": rows,
        "code": code or "",
        "engine": engine,
        "success": False,
        "attempts": attempts,
        "aggregate_only": True,
        "error": error or "SQL generation failed",
    }


async def run_question_aware_analytics(
    data: Union[pd.DataFrame, DatasetHandle],
    user_question: str,
    model: str,
    chat_completion_fn: Callable[..., Awaitable[Any]],
    column_mapping: Optional[Dict[str, str]] = None,
    *,
    max_llm_attempts: int = 2,
) -> Optional[Dict[str, Any]]:
    """Generate and execute DuckDB SQL on the full dataset (all sizes)."""
    handle = as_handle(data)
    question = (user_question or "").strip()
    if not question or handle.row_count() == 0:
        return None
    return await _run_duckdb_analytics(
        handle,
        question,
        model,
        chat_completion_fn,
        column_mapping,
        max_llm_attempts=max_llm_attempts,
    )


def merge_into_analytics(
    analytics_results: Optional[Dict[str, Any]],
    question_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    base = dict(analytics_results or {})
    notes = base.get("formatted_notes", "") or ""

    if question_result and question_result.get("formatted"):
        if question_result.get("agent_used") and question_result.get("step_count", 1) > 1:
            header = (
                f"\n\n=== Multi-Step Question Analysis "
                f"({question_result['step_count']} steps, computed on full dataset) ===\n"
            )
        else:
            header = "\n\n=== Question-Specific Analysis (computed on full dataset) ===\n"
        qa_block = f"{header}{question_result['formatted']}"
        base["formatted_notes"] = (notes + qa_block).strip()
        base["question_aware"] = question_result

    if question_result:
        existing_findings = list(base.get("structured_findings") or [])
        existing_ids = {item.get("id") for item in existing_findings}
        existing_findings.extend(
            item
            for item in question_result.get("structured_findings") or []
            if item.get("id") not in existing_ids
        )
        if existing_findings:
            base["structured_findings"] = existing_findings
        if question_result.get("agent_tool_calls"):
            base["agent_tool_calls"] = list(question_result["agent_tool_calls"])
        if question_result.get("agent_decisions"):
            base["agent_decisions"] = list(question_result["agent_decisions"])
        if question_result.get("agent_stop_reason"):
            base["agent_stop_reason"] = question_result["agent_stop_reason"]

    chart_hints: List[Dict[str, Any]] = list(base.get("chart_hints") or [])
    if question_result and question_result.get("chart_hint"):
        chart_hints.append(question_result["chart_hint"])
    for step in (question_result or {}).get("steps") or []:
        if step.get("chart_hint"):
            chart_hints.append(step["chart_hint"])
    if chart_hints:
        base["chart_hints"] = chart_hints

    web_sources: List[Dict[str, Any]] = list(base.get("web_sources") or [])
    if question_result and question_result.get("web_sources"):
        web_sources.extend(question_result["web_sources"])
    for step in (question_result or {}).get("steps") or []:
        if step.get("web_sources"):
            web_sources.extend(step["web_sources"])
    web_sources = dedupe_web_sources(web_sources)
    if web_sources:
        base["web_sources"] = web_sources

    return base


def format_specific_insight(question_result: Optional[Dict[str, Any]]) -> str:
    if not question_result or not question_result.get("formatted"):
        return ""
    return (
        f"\n<specific_query_result>\n"
        f"{question_result['formatted']}\n"
        f"</specific_query_result>\n"
    )
