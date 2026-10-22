"""
Extended DuckDB analytics — parity with Pandas path in ChatService analytics.
Runs on full dataset without loading into memory.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd

from app.core.config import settings
from app.services.dataset_engine import DatasetHandle, _quote_ident

_CORR_THRESHOLD = 0.3
_OUTLIER_Z = 2.8
_MAX_CATEGORIES = 99
_MIN_CATEGORY_CARDINALITY = 2


def _numeric_columns_from_summarize(summary: pd.DataFrame) -> List[str]:
    cols: List[str] = []
    for _, row in summary.iterrows():
        ctype = str(row.get("column_type", "")).upper()
        if any(t in ctype for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "BIGINT")):
            cols.append(str(row["column_name"]))
    return cols


def _categorical_columns(handle: DatasetHandle, numeric: List[str]) -> List[str]:
    numeric_set = set(numeric)
    cats: List[str] = []
    for col in handle.column_names():
        if col in numeric_set:
            continue
        q = _quote_ident(col)
        try:
            distinct = int(
                handle._con.execute(
                    f"SELECT COUNT(DISTINCT {q}) FROM {handle._table} WHERE {q} IS NOT NULL"
                ).fetchone()[0]
            )
            if _MIN_CATEGORY_CARDINALITY < distinct < _MAX_CATEGORIES:
                cats.append(col)
        except Exception:
            continue
    return cats


def _resolve_time_column(handle: DatasetHandle, role_to_col: Dict[str, str]) -> Optional[str]:
    for role in ("date", "timestamp", "time", "period"):
        col = role_to_col.get(role)
        if col and col in handle.column_names():
            return col
    for col in handle.column_names():
        lower = col.lower()
        if any(k in lower for k in ("date", "time", "timestamp", "วันที่", "เวลา")):
            return col
    return None


def _monthly_sums(handle: DatasetHandle, time_col: str, value_col: str) -> List[Tuple[str, float]]:
    tq, vq = _quote_ident(time_col), _quote_ident(value_col)
    sql = f"""
        SELECT date_trunc('month', try_cast({tq} AS TIMESTAMP)) AS m,
               SUM(try_cast({vq} AS DOUBLE)) AS total
        FROM {handle._table}
        WHERE {tq} IS NOT NULL AND try_cast({vq} AS DOUBLE) IS NOT NULL
        GROUP BY 1
        HAVING m IS NOT NULL
        ORDER BY 1
    """
    try:
        rows = handle._con.execute(sql).fetchall()
        return [(str(r[0])[:7], float(r[1] or 0)) for r in rows if r[0] is not None]
    except Exception:
        return []


def append_extended_duckdb_analytics(
    handle: DatasetHandle,
    role_to_col: Dict[str, str],
    summarize_df: Optional[pd.DataFrame] = None,
) -> List[str]:
    """Time series, categorical breakdowns, correlations, outliers on full DuckDB table."""
    lines: List[str] = []
    summary = summarize_df if summarize_df is not None else handle.summarize_df()
    numeric = _numeric_columns_from_summarize(summary)
    if not numeric:
        return lines

    rows = handle.row_count()
    skip_expensive = rows > settings.EXTENDED_ANALYTICS_ROW_THRESHOLD

    lines.append("\n=== Summary Statistics (full dataset, DuckDB) ===")
    for _, row in summary.iterrows():
        col = str(row.get("column_name", ""))
        if col not in numeric[:20]:
            continue
        ctype = str(row.get("column_type", "")).upper()
        if not any(t in ctype for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "BIGINT")):
            continue
        null_pct = float(row.get("null_percentage") or 0)
        miss = f" (Missing: {null_pct:.1f}%)" if null_pct > 0 else ""
        sum_v = row.get("sum")
        if sum_v is not None:
            lines.append(
                f"- **{col.upper()}**: Sum: {float(sum_v):,.2f} | Avg: {float(row.get('avg') or 0):,.2f} | "
                f"Range: [{float(row.get('min') or 0):,.2f} to {float(row.get('max') or 0):,.2f}]{miss}"
            )

    sales_col = role_to_col.get("sales")
    cost_col = role_to_col.get("cost")
    if sales_col and cost_col and sales_col in handle.column_names() and cost_col in handle.column_names():
        sq, cq = _quote_ident(sales_col), _quote_ident(cost_col)
        row = handle._con.execute(
            f"""
            SELECT SUM(try_cast({sq} AS DOUBLE)), SUM(try_cast({cq} AS DOUBLE))
            FROM {handle._table}
            """
        ).fetchone()
        if row and row[0]:
            sales_val, cost_val = float(row[0] or 0), float(row[1] or 0)
            profit = sales_val - cost_val
            margin = (profit / sales_val * 100) if sales_val else 0
            lines.append(
                f"- **FINANCIAL OVERVIEW**: Gross Profit: {profit:,.2f} | Profit Margin: {margin:.2f}%"
            )

    time_col = _resolve_time_column(handle, role_to_col)
    if time_col and numeric:
        lines.append("\n=== Time-Series Trends & Monthly Breakdowns (DuckDB) ===")
        for ncol in numeric[:8]:
            monthly = _monthly_sums(handle, time_col, ncol)
            if len(monthly) >= 1:
                lines.append(f"- **{ncol.upper()} Monthly Sums**:")
                for period, val in monthly[-12:]:
                    lines.append(f"  * {period}: {val:,.2f}")
                if len(monthly) >= 2:
                    prev, last = monthly[-2][1], monthly[-1][1]
                    if prev:
                        growth = ((last - prev) / prev) * 100
                        direction = "increased" if growth > 0 else "decreased"
                        lines.append(
                            f"  * MoM Growth ({monthly[-2][0]} to {monthly[-1][0]}): {growth:+.2f}% ({direction})"
                        )

    if skip_expensive:
        lines.append(
            f"\n(Skipped categorical/correlation/outlier scans — dataset has {rows:,} rows; "
            f"threshold {settings.EXTENDED_ANALYTICS_ROW_THRESHOLD:,}. "
            "Use question-specific SQL for deep breakdowns.)"
        )
        return lines

    categorical = _categorical_columns(handle, numeric)
    if categorical and numeric:
        lines.append("\n=== Categorical Breakdowns & Top Performers (DuckDB) ===")
        for cat_col in categorical[:5]:
            cq = _quote_ident(cat_col)
            for num_col in numeric[:5]:
                nq = _quote_ident(num_col)
                try:
                    top = handle._con.execute(
                        f"""
                        SELECT {cq}, SUM(try_cast({nq} AS DOUBLE)) AS s
                        FROM {handle._table}
                        WHERE {cq} IS NOT NULL
                        GROUP BY 1
                        ORDER BY s DESC NULLS LAST
                        LIMIT 1
                        """
                    ).fetchone()
                    total = handle._con.execute(
                        f"SELECT SUM(try_cast({nq} AS DOUBLE)) FROM {handle._table}"
                    ).fetchone()
                    if top and top[0] is not None and total and total[0]:
                        pct = float(top[1] or 0) / float(total[0]) * 100
                        lines.append(
                            f"- **Top {cat_col.upper()}** (by {num_col.upper()}): **{top[0]}** "
                            f"with {float(top[1] or 0):,.2f} ({pct:.1f}% of total)"
                        )
                except Exception:
                    continue

    if len(numeric) >= 2:
        lines.append("\n=== Statistically Mapped Relationships (DuckDB) ===")
        found = False
        unique = list(dict.fromkeys(numeric))[:10]
        for i, c1 in enumerate(unique):
            for c2 in unique[i + 1 :]:
                q1, q2 = _quote_ident(c1), _quote_ident(c2)
                try:
                    r = handle._con.execute(
                        f"""
                        SELECT CORR(try_cast({q1} AS DOUBLE), try_cast({q2} AS DOUBLE))
                        FROM {handle._table}
                        WHERE try_cast({q1} AS DOUBLE) IS NOT NULL
                          AND try_cast({q2} AS DOUBLE) IS NOT NULL
                        """
                    ).fetchone()
                    if r and r[0] is not None and abs(float(r[0])) > _CORR_THRESHOLD:
                        found = True
                        rv = float(r[0])
                        rel = "positive/direct" if rv > 0 else "negative/inverse"
                        strength = "strong" if abs(rv) > 0.7 else "moderate"
                        lines.append(
                            f"- Mapped relationship between **{c1.upper()}** and **{c2.upper()}** "
                            f"is {strength} {rel} (r = {rv:+.2f})"
                        )
                except Exception:
                    continue
        if not found:
            lines.append("- No statistically moderate or strong linear relationships detected between variables.")

    outlier_notes: List[str] = []
    for col in numeric[:15]:
        q = _quote_ident(col)
        try:
            cnt = handle._con.execute(
                f"""
                WITH stats AS (
                    SELECT AVG(try_cast({q} AS DOUBLE)) AS m,
                           STDDEV(try_cast({q} AS DOUBLE)) AS s
                    FROM {handle._table}
                    WHERE try_cast({q} AS DOUBLE) IS NOT NULL
                )
                SELECT COUNT(*) FROM {handle._table}, stats
                WHERE stats.s > 0
                  AND ABS(try_cast({q} AS DOUBLE) - stats.m) > {_OUTLIER_Z} * stats.s
                """
            ).fetchone()
            if cnt and int(cnt[0]) > 0:
                outlier_notes.append(
                    f"- Detected {int(cnt[0])} anomalous data points in **{col.upper()}** "
                    f"(exceeding {_OUTLIER_Z} standard deviations)"
                )
        except Exception:
            continue
    if outlier_notes:
        lines.append("\n=== Data Anomaly Warnings (DuckDB) ===")
        lines.extend(outlier_notes)

    return lines
