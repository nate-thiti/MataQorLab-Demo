"""Standard cleaning for messy tabular data before semantic mapping and analytics."""
from __future__ import annotations

import re
import warnings
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import pandas as pd

from app.core.json_safety import to_json_safe

if TYPE_CHECKING:
    from app.services.dataset_engine import DatasetHandle

_EMPTY_MARKERS = frozenset(
    {"", "na", "n/a", "null", "none", "-", "--", "nan", "n.a.", "#n/a", "#null!"}
)
_DATE_MAPPINGS = frozenset({"date", "timestamp", "due_date"})
_CURRENCY_RE = re.compile(r"[฿$€£¥₩₹]|,\s?(?=\d{3})")
_MERGED_NULL_RATIO = 0.15
_MOSTLY_EMPTY_ROW_RATIO = 0.8
_PROFILE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "standard": {
        "drop_empty_rows": True,
        "drop_empty_columns": True,
        "drop_mostly_empty_rows": False,
        "dedupe": True,
        "ffill": True,
        "coerce_dates": True,
        "strip_currency": True,
        "infer_types": False,
        "merged_null_ratio": _MERGED_NULL_RATIO,
    },
    "financial": {
        "drop_empty_rows": True,
        "drop_empty_columns": True,
        "drop_mostly_empty_rows": False,
        "dedupe": False,
        "ffill": False,
        "coerce_dates": True,
        "strip_currency": True,
        "infer_types": False,
        "merged_null_ratio": _MERGED_NULL_RATIO,
    },
    "conservative": {
        "drop_empty_rows": False,
        "drop_empty_columns": False,
        "drop_mostly_empty_rows": False,
        "dedupe": False,
        "ffill": False,
        "coerce_dates": False,
        "strip_currency": False,
        "infer_types": False,
        "merged_null_ratio": _MERGED_NULL_RATIO,
    },
    "aggressive": {
        "drop_empty_rows": True,
        "drop_empty_columns": True,
        "drop_mostly_empty_rows": True,
        "dedupe": True,
        "ffill": True,
        "coerce_dates": True,
        "strip_currency": True,
        "infer_types": True,
        "merged_null_ratio": 0.08,
    },
}


def resolve_cleaning_profile(profile: str = "standard") -> Tuple[str, Dict[str, Any]]:
    name = (profile or "standard").strip().lower()
    if name not in _PROFILE_DEFAULTS:
        name = "standard"
    return name, dict(_PROFILE_DEFAULTS[name])


def _infer_series_type(series: pd.Series) -> Tuple[str, float]:
    non_null = series.dropna()
    if non_null.empty:
        return "empty", 1.0
    if pd.api.types.is_numeric_dtype(non_null):
        return "numeric", 0.98
    if pd.api.types.is_datetime64_any_dtype(non_null):
        return "date", 0.98
    as_text = non_null.astype(str)
    numeric_rate = pd.to_numeric(as_text.map(strip_currency_text), errors="coerce").notna().mean()
    if numeric_rate >= 0.9:
        return "numeric", float(numeric_rate)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        date_rate = pd.to_datetime(as_text, errors="coerce").notna().mean()
    if date_rate >= 0.85:
        return "date", float(date_rate)
    unique_ratio = non_null.nunique(dropna=True) / max(len(non_null), 1)
    if unique_ratio <= 0.5:
        return "category", float(1 - unique_ratio)
    return "text", 0.7


def _schema_profile_dataframe(
    df: pd.DataFrame,
    column_mapping: Optional[Dict[str, str]],
) -> Dict[str, Dict[str, Any]]:
    profile: Dict[str, Dict[str, Any]] = {}
    if df is None or df.empty:
        return profile
    total = max(len(df), 1)
    for col in df.columns:
        inferred_type, confidence = _infer_series_type(df[col])
        role = _mapped_role(column_mapping, str(col))
        null_count = int(df[col].isna().sum())
        profile[str(col)] = {
            "inferred_type": inferred_type,
            "semantic_role": role or None,
            "confidence": round(confidence, 3),
            "null_count": null_count,
            "null_rate": round(null_count / total, 4),
        }
    return profile


def _preview_records(df: pd.DataFrame, limit: int = 5) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    preview = df.head(limit).where(pd.notna(df.head(limit)), None)
    records = preview.to_dict(orient="records")
    return to_json_safe(records)


def _quality_score(report: Dict[str, Any]) -> int:
    rows_before = max(int(report.get("rows_before") or 0), 1)
    penalties = 0.0
    penalties += min(30.0, (int(report.get("dropped_empty_rows") or 0) / rows_before) * 80)
    penalties += min(25.0, (int(report.get("dropped_duplicates") or 0) / rows_before) * 70)
    penalties += min(20.0, (sum(report.get("invalid_dates", {}).values()) / rows_before) * 60)
    penalties += min(20.0, (sum(report.get("coerced_numeric", {}).values()) / rows_before) * 60)
    penalties += min(15.0, len(report.get("dropped_columns", [])) * 3)
    return max(0, min(100, int(round(100 - penalties))))


def _report_notes(report: Dict[str, Any]) -> List[str]:
    notes: List[str] = []
    if report.get("dropped_columns"):
        notes.append(f"Dropped {len(report['dropped_columns'])} all-empty column(s).")
    if report.get("forward_filled_columns"):
        cols = report["forward_filled_columns"]
        notes.append(
            f"Forward-filled merged-cell gaps in: {', '.join(cols[:5])}"
            + (f" (+{len(cols) - 5} more)" if len(cols) > 5 else "")
        )
    if report.get("dropped_duplicates"):
        notes.append(f"Removed {report['dropped_duplicates']} duplicate row(s).")
    if report.get("dropped_empty_rows"):
        notes.append(f"Dropped {report['dropped_empty_rows']} all-empty row(s).")
    if report.get("dropped_mostly_empty_rows"):
        notes.append(f"Dropped {report['dropped_mostly_empty_rows']} mostly-empty row(s).")
    for col, count in report.get("invalid_dates", {}).items():
        notes.append(f"Column '{col}': {count} value(s) could not be parsed as dates.")
    for col, count in report.get("coerced_numeric", {}).items():
        notes.append(f"Column '{col}': {count} non-numeric value(s) after currency cleanup.")
    return notes


def strip_currency_text(value) -> object:
    """Remove common currency symbols and grouping commas from string numerics."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return value
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return text
    text = _CURRENCY_RE.sub("", text)
    text = text.replace(",", "").replace(" ", "")
    return text.strip() or text


def normalize_empty(value) -> object:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return pd.NA
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() in _EMPTY_MARKERS:
            return pd.NA
        return stripped
    return value


def _mapped_role(column_mapping: Optional[Dict[str, str]], col_name: str) -> str:
    if not column_mapping:
        return ""
    return (column_mapping.get(col_name) or "").strip().lower()


def _detect_merged_cell_columns(
    df: pd.DataFrame,
    merged_null_ratio: float = _MERGED_NULL_RATIO,
) -> List[str]:
    """Columns that look like Excel merged-cell gaps (sparse nulls in mostly-text columns)."""
    candidates: List[str] = []
    for col in df.columns:
        series = df[col]
        if series.dtype != object and not pd.api.types.is_string_dtype(series):
            continue
        non_null = series.notna().sum()
        if non_null == 0:
            continue
        null_ratio = 1 - (non_null / len(df))
        if null_ratio < merged_null_ratio:
            continue
        filled = series.ffill()
        if filled.notna().sum() <= non_null:
            continue
        candidates.append(str(col))
    return candidates


def _strip_column_names(df: pd.DataFrame) -> pd.DataFrame:
    rename = {col: str(col).strip() for col in df.columns}
    if rename != dict(zip(df.columns, df.columns)):
        df = df.rename(columns=rename)
    return df


def clean_dataframe(
    df: pd.DataFrame,
    column_mapping: Optional[Dict[str, str]] = None,
    cleaning_profile: str = "standard",
    cleaning_recipe: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], pd.DataFrame]:
    """Apply standard cleaning to an in-memory dataframe."""
    if df is None or df.empty:
        return [], df

    profile_name, options = resolve_cleaning_profile(cleaning_profile)
    if isinstance(cleaning_recipe, dict):
        rule_overrides = cleaning_recipe.get("rules")
        if isinstance(rule_overrides, dict):
            for key in options:
                if key in rule_overrides and isinstance(rule_overrides[key], bool):
                    options[key] = rule_overrides[key]
    work = _strip_column_names(df.copy())
    before_rows = len(work)
    before_cols = list(work.columns)
    report: Dict[str, Any] = {
        "profile": profile_name,
        "engine": "pandas",
        "rows_before": before_rows,
        "columns_before": [str(c) for c in before_cols],
        "rows_after": before_rows,
        "columns_after": [],
        "dropped_empty_rows": 0,
        "dropped_mostly_empty_rows": 0,
        "dropped_duplicates": 0,
        "dropped_columns": [],
        "forward_filled_columns": [],
        "coerced_numeric": {},
        "invalid_dates": {},
        "schema_profile": {},
        "preview": {"before": _preview_records(work), "after": []},
        "lineage": {
            "source": "dataframe",
            "clean_version": "standard_v1",
            "transform": "transform-on-analyze",
            "mapping_columns": list((column_mapping or {}).keys()),
        },
    }

    for col in list(work.columns):
        if work[col].dtype == object or pd.api.types.is_string_dtype(work[col]):
            work[col] = work[col].map(normalize_empty)
        else:
            work[col] = work[col].where(work[col].notna(), pd.NA)

    if options.get("drop_mostly_empty_rows"):
        mostly_empty = work.isna().mean(axis=1) >= _MOSTLY_EMPTY_ROW_RATIO
        mostly_empty_count = int(mostly_empty.sum())
        if mostly_empty_count:
            work = work.loc[~mostly_empty]
            report["dropped_mostly_empty_rows"] = mostly_empty_count

    if options.get("drop_empty_rows", True):
        empty_rows = int(work.isna().all(axis=1).sum())
        if empty_rows:
            work = work.dropna(how="all")
            report["dropped_empty_rows"] = empty_rows

    if options.get("drop_empty_columns", True):
        empty_cols = [str(c) for c in work.columns if work[c].isna().all()]
        if empty_cols:
            work = work.drop(columns=empty_cols)
            report["dropped_columns"] = empty_cols

    merged_ratio = float(options.get("merged_null_ratio", _MERGED_NULL_RATIO))
    merged_cols = (
        _detect_merged_cell_columns(work, merged_ratio) if options["ffill"] else []
    )
    if merged_cols:
        for col in merged_cols:
            work[col] = work[col].ffill()
        report["forward_filled_columns"] = merged_cols

    dupes = int(work.duplicated().sum()) if options["dedupe"] else 0
    if dupes:
        work = work.drop_duplicates()
        report["dropped_duplicates"] = dupes

    from app.services.dataset_engine import _NUMERIC_MAPPINGS

    for col in work.columns:
        role = _mapped_role(column_mapping, str(col))
        inferred_type = ""
        if options.get("infer_types") and not role:
            inferred_type, _ = _infer_series_type(work[col])
        coerce_date = options["coerce_dates"] and (
            role in _DATE_MAPPINGS or (options.get("infer_types") and inferred_type == "date")
        )
        if coerce_date:
            parsed = pd.to_datetime(work[col], errors="coerce", dayfirst=False)
            bad = work[col].notna() & parsed.isna()
            if bad.any():
                report["invalid_dates"][str(col)] = int(bad.sum())
            work[col] = parsed
            continue
        strip_numeric = options["strip_currency"] and (
            role in _NUMERIC_MAPPINGS
            or (options.get("infer_types") and inferred_type == "numeric")
        )
        if strip_numeric and (
            work[col].dtype == object or pd.api.types.is_string_dtype(work[col])
        ):
            stripped = work[col].map(strip_currency_text)
            numeric = pd.to_numeric(stripped, errors="coerce")
            bad = work[col].notna() & numeric.isna()
            if bad.any():
                report["coerced_numeric"][str(col)] = int(bad.sum())
            work[col] = numeric

    if isinstance(cleaning_recipe, dict):
        from app.services.etl_pipeline import apply_recipe_dataframe

        work, recipe_audit = apply_recipe_dataframe(work, cleaning_recipe, column_mapping)
        report["recipe_audit"] = recipe_audit

    report["rows_after"] = len(work)
    report["columns_after"] = [str(c) for c in work.columns]
    report["preview"]["after"] = _preview_records(work)
    report["schema_profile"] = _schema_profile_dataframe(work, column_mapping)
    report["quality_score"] = _quality_score(report)
    work.attrs["cleaning_report"] = report

    return _report_notes(report), work


def clean_handle_duckdb(
    handle: "DatasetHandle",
    column_mapping: Optional[Dict[str, str]] = None,
    cleaning_profile: str = "standard",
    cleaning_recipe: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], "DatasetHandle"]:
    """SQL-based cleaning for large DuckDB-backed datasets."""
    from app.services.dataset_engine import TABLE_NAME, _quote_ident

    profile_name, options = resolve_cleaning_profile(cleaning_profile)
    if isinstance(cleaning_recipe, dict):
        rule_overrides = cleaning_recipe.get("rules")
        if isinstance(rule_overrides, dict):
            for key in options:
                if key in rule_overrides and isinstance(rule_overrides[key], bool):
                    options[key] = rule_overrides[key]
    raw = handle._ensure_raw_table()
    before = handle.row_count()
    order_col = "__clean_order"

    describe = handle._con.execute(f"DESCRIBE {raw}").fetchall()
    col_types = {row[0]: str(row[1]).upper() for row in describe}
    cols = list(col_types.keys())
    report: Dict[str, Any] = {
        "profile": profile_name,
        "engine": "duckdb",
        "rows_before": before,
        "columns_before": [str(c) for c in cols],
        "rows_after": before,
        "columns_after": [],
        "dropped_empty_rows": 0,
        "dropped_mostly_empty_rows": 0,
        "dropped_duplicates": 0,
        "dropped_columns": [],
        "forward_filled_columns": [],
        "coerced_numeric": {},
        "invalid_dates": {},
        "schema_profile": {},
        "preview": {"before": [], "after": []},
        "lineage": {
            "source": "duckdb_handle",
            "clean_version": "standard_v1",
            "transform": "transform-on-analyze",
            "mapping_columns": list((column_mapping or {}).keys()),
        },
    }
    report["preview"]["before"] = _preview_records(
        handle._con.execute(f"SELECT * FROM {raw} LIMIT 5").df()
    )
    type_sample = handle._con.execute(f"SELECT * FROM {raw} LIMIT 5000").df()

    select_parts: List[str] = []
    for col in cols:
        q = _quote_ident(col)
        ctype = col_types[col]
        role = _mapped_role(column_mapping, col)
        inferred_type = ""
        if options.get("infer_types") and not role and col in type_sample.columns:
            inferred_type, _ = _infer_series_type(type_sample[col])
        if "VARCHAR" in ctype or "STRING" in ctype or "BLOB" in ctype:
            trimmed = f"TRIM(CAST({q} AS VARCHAR))"
            null_expr = (
                f"CASE WHEN LOWER({trimmed}) IN "
                f"('','na','n/a','null','none','-','--','nan','n.a.','#n/a') "
                f"THEN NULL ELSE {trimmed} END"
            )
            coerce_date = options["coerce_dates"] and (
                role in _DATE_MAPPINGS
                or (options.get("infer_types") and inferred_type == "date")
            )
            if coerce_date:
                bad_dates = int(
                    handle._con.execute(
                        f"SELECT SUM(CASE WHEN {null_expr} IS NOT NULL "
                        f"AND TRY_CAST({null_expr} AS TIMESTAMP) IS NULL THEN 1 ELSE 0 END) FROM {raw}"
                    ).fetchone()[0]
                    or 0
                )
                if bad_dates:
                    report["invalid_dates"][str(col)] = bad_dates
                select_parts.append(f"TRY_CAST({null_expr} AS TIMESTAMP) AS {q}")
            else:
                from app.services.dataset_engine import _NUMERIC_MAPPINGS

                strip_numeric = options["strip_currency"] and (
                    role in _NUMERIC_MAPPINGS
                    or (options.get("infer_types") and inferred_type == "numeric")
                )
                if strip_numeric:
                    stripped = (
                        f"REGEXP_REPLACE(REGEXP_REPLACE({null_expr}, '[฿$€£¥₩₹]', ''), ',', '')"
                    )
                    bad_numeric = int(
                        handle._con.execute(
                            f"SELECT SUM(CASE WHEN {null_expr} IS NOT NULL "
                            f"AND TRY_CAST({stripped} AS DOUBLE) IS NULL THEN 1 ELSE 0 END) FROM {raw}"
                        ).fetchone()[0]
                        or 0
                    )
                    if bad_numeric:
                        report["coerced_numeric"][str(col)] = bad_numeric
                    select_parts.append(f"{stripped} AS {q}")
                else:
                    select_parts.append(f"{null_expr} AS {q}")
        else:
            select_parts.append(q)

    distinct_keyword = "DISTINCT " if options["dedupe"] else ""
    clean_table = f"{TABLE_NAME}_clean"
    handle._con.execute(f"DROP TABLE IF EXISTS {clean_table}")
    select_sql = f"SELECT {distinct_keyword}{', '.join(select_parts)} FROM {raw}"
    if options["dedupe"]:
        handle._con.execute(
            f"CREATE TABLE {clean_table} AS "
            f"SELECT *, ROW_NUMBER() OVER () AS {_quote_ident(order_col)} FROM ({select_sql}) cleaned"
        )
    else:
        handle._con.execute(
            f"CREATE TABLE {clean_table} AS "
            f"SELECT {', '.join(select_parts)}, ROW_NUMBER() OVER () AS {_quote_ident(order_col)} FROM {raw}"
        )

    clean_describe = handle._con.execute(f"DESCRIBE {clean_table}").fetchall()
    clean_cols = [row[0] for row in clean_describe if row[0] != order_col]
    empty_row_count = 0
    if clean_cols and options.get("drop_mostly_empty_rows"):
        null_parts = [
            f"CASE WHEN {_quote_ident(col)} IS NULL THEN 1 ELSE 0 END" for col in clean_cols
        ]
        null_threshold = max(1, int(len(clean_cols) * _MOSTLY_EMPTY_ROW_RATIO))
        mostly_empty_expr = " + ".join(null_parts)
        mostly_empty_count = int(
            handle._con.execute(
                f"SELECT COUNT(*) FROM {clean_table} "
                f"WHERE ({mostly_empty_expr}) >= {null_threshold}"
            ).fetchone()[0]
            or 0
        )
        if mostly_empty_count:
            handle._con.execute(
                f"CREATE TABLE {TABLE_NAME}_mostly AS "
                f"SELECT * FROM {clean_table} "
                f"WHERE ({mostly_empty_expr}) < {null_threshold} "
                f"ORDER BY {_quote_ident(order_col)}"
            )
            handle._con.execute(f"DROP TABLE {clean_table}")
            handle._con.execute(f"ALTER TABLE {TABLE_NAME}_mostly RENAME TO {clean_table}")
            report["dropped_mostly_empty_rows"] = mostly_empty_count

    if clean_cols and options.get("drop_empty_columns", True):
        count_exprs = [f"COUNT({_quote_ident(col)})" for col in clean_cols]
        count_row = handle._con.execute(
            f"SELECT {', '.join(count_exprs)} FROM {clean_table}"
        ).fetchone()
        non_empty_cols = [
            col for col, value in zip(clean_cols, count_row or []) if int(value or 0) > 0
        ]
        dropped_cols = len(clean_cols) - len(non_empty_cols)
        if dropped_cols and non_empty_cols:
            projected_table = f"{TABLE_NAME}_projected"
            handle._con.execute(f"DROP TABLE IF EXISTS {projected_table}")
            handle._con.execute(
                f"CREATE TABLE {projected_table} AS "
                f"SELECT {', '.join(_quote_ident(col) for col in non_empty_cols)}, {_quote_ident(order_col)} "
                f"FROM {clean_table} ORDER BY {_quote_ident(order_col)}"
            )
            handle._con.execute(f"DROP TABLE {clean_table}")
            handle._con.execute(f"ALTER TABLE {projected_table} RENAME TO {clean_table}")
            report["dropped_columns"] = [col for col in clean_cols if col not in non_empty_cols]
            clean_cols = non_empty_cols
        elif dropped_cols:
            handle._con.execute(f"DELETE FROM {clean_table}")

    clean_cols = [
        row[0]
        for row in handle._con.execute(f"DESCRIBE {clean_table}").fetchall()
        if row[0] != order_col
    ]
    if clean_cols and options.get("drop_empty_rows", True):
        all_null_expr = " AND ".join(f"{_quote_ident(col)} IS NULL" for col in clean_cols)
        empty_row_count = int(
            handle._con.execute(
                f"SELECT COUNT(*) FROM {clean_table} WHERE {all_null_expr}"
            ).fetchone()[0]
            or 0
        )
        if empty_row_count:
            keep_expr = " OR ".join(f"{_quote_ident(col)} IS NOT NULL" for col in clean_cols)
            filtered_table = f"{TABLE_NAME}_filtered"
            handle._con.execute(f"DROP TABLE IF EXISTS {filtered_table}")
            handle._con.execute(
                f"CREATE TABLE {filtered_table} AS "
                f"SELECT * FROM {clean_table} WHERE {keep_expr} ORDER BY {_quote_ident(order_col)}"
            )
            handle._con.execute(f"DROP TABLE {clean_table}")
            handle._con.execute(f"ALTER TABLE {filtered_table} RENAME TO {clean_table}")
            report["dropped_empty_rows"] = empty_row_count

    clean_cols = [
        row[0]
        for row in handle._con.execute(f"DESCRIBE {clean_table}").fetchall()
        if row[0] != order_col
    ]
    after = int(handle._con.execute(f"SELECT COUNT(*) FROM {clean_table}").fetchone()[0])
    if after < before:
        removed = before - after
        if not report["dropped_empty_rows"] and not report.get("dropped_mostly_empty_rows"):
            report["dropped_empty_rows"] = min(empty_row_count, removed)
        if options["dedupe"]:
            already_dropped = report["dropped_empty_rows"] + int(report.get("dropped_mostly_empty_rows") or 0)
            report["dropped_duplicates"] = max(0, removed - already_dropped)

    sample = handle._con.execute(
        f"SELECT {', '.join(_quote_ident(col) for col in clean_cols)} "
        f"FROM {clean_table} ORDER BY {_quote_ident(order_col)} LIMIT 5000"
    ).df()
    merged_ratio = float(options.get("merged_null_ratio", _MERGED_NULL_RATIO))
    merged_cols = (
        _detect_merged_cell_columns(sample, merged_ratio) if options["ffill"] else []
    )
    clean_cols = [
        row[0]
        for row in handle._con.execute(f"DESCRIBE {clean_table}").fetchall()
        if row[0] != order_col
    ]
    valid_merged = [c for c in merged_cols if c in clean_cols]
    if valid_merged:
        rn_table = f"{TABLE_NAME}_rn"
        handle._con.execute(f"DROP TABLE IF EXISTS {rn_table}")
        handle._con.execute(
            f"CREATE TABLE {rn_table} AS "
            f"SELECT *, ROW_NUMBER() OVER () AS __rn FROM {clean_table}"
        )
        ffill_parts = []
        for col in clean_cols:
            q = _quote_ident(col)
            if col in valid_merged:
                ffill_parts.append(
                    f"LAST_VALUE({q} IGNORE NULLS) OVER (ORDER BY {_quote_ident(order_col)}) AS {q}"
                )
            else:
                ffill_parts.append(q)
        ffill_parts.append(_quote_ident(order_col))
        handle._con.execute(f"DROP TABLE {clean_table}")
        handle._con.execute(
            f"CREATE TABLE {clean_table} AS "
            f"SELECT {', '.join(ffill_parts)} FROM {rn_table} ORDER BY {_quote_ident(order_col)}"
        )
        handle._con.execute(f"DROP TABLE {rn_table}")
        report["forward_filled_columns"] = valid_merged

    handle._con.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}_final")
    handle._con.execute(
        f"CREATE TABLE {TABLE_NAME}_final AS "
        f"SELECT {', '.join(_quote_ident(col) for col in clean_cols)} "
        f"FROM {clean_table} ORDER BY {_quote_ident(order_col)}"
    )
    handle._con.execute(f"DROP TABLE {clean_table}")
    handle._con.execute(f"ALTER TABLE {TABLE_NAME}_final RENAME TO {clean_table}")
    handle._con.execute(f"DROP TABLE {raw}")
    handle._con.execute(f"ALTER TABLE {clean_table} RENAME TO {raw}")
    handle._raw_table = raw
    handle._con.execute(f"DROP VIEW IF EXISTS {TABLE_NAME}")
    handle._con.execute(f"CREATE VIEW {TABLE_NAME} AS SELECT * FROM {raw}")
    handle.invalidate_summarize_cache()
    final_df = handle._con.execute(f"SELECT * FROM {TABLE_NAME} LIMIT 5000").df()
    handle._cached_row_count = int(handle._con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0])
    report["rows_after"] = handle._cached_row_count
    report["columns_after"] = handle.column_names()
    report["preview"]["after"] = _preview_records(final_df)
    report["schema_profile"] = _schema_profile_dataframe(final_df, column_mapping)
    report["quality_score"] = _quality_score(report)
    handle._cleaning_report = report
    if isinstance(cleaning_recipe, dict):
        from app.services.etl_pipeline import apply_recipe_duckdb

        report["recipe_audit"] = apply_recipe_duckdb(handle, cleaning_recipe, column_mapping)
        report["rows_after"] = handle.row_count()
        report["columns_after"] = handle.column_names()
        report["preview"]["after"] = _preview_records(handle.to_pandas(limit=5))
        handle._cleaning_report = report
    return _report_notes(report), handle


def prepare_handle_for_analysis(
    handle: "DatasetHandle",
    column_mapping: Optional[Dict[str, str]] = None,
) -> Tuple[List[str], "DatasetHandle"]:
    """Run standard cleaning then semantic mapping coercion."""
    return handle.prepare_for_analysis(column_mapping)
