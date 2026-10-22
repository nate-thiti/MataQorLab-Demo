"""
DuckDB-backed dataset handle for large tables — avoids full in-memory Pandas when row count exceeds threshold.
"""
import hashlib
import io
import json
import os
import re
import tempfile
from typing import Dict, List, Optional, Tuple, Union

import duckdb
import pandas as pd

from app.core.config import settings
from app.core.parser import detect_header_row_from_path
from app.services.column_profile import build_column_profile

TABLE_NAME = "df"
RAW_TABLE_SUFFIX = "_raw"
FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke)\b",
    re.IGNORECASE,
)

_NUMERIC_MAPPINGS = frozenset(
    {
        "num",
        "sales",
        "qty",
        "quantity",
        "cost",
        "stock_in",
        "stock_out",
        "stock_level",
        "salary",
        "defects",
        "output",
        "downtime",
        "ad_spend",
        "clicks",
        "impressions",
        "satisfaction_score",
        "resolution_time",
        "lead_time",
        "tenure",
    }
)


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _escape_path(path: str) -> str:
    return path.replace("'", "''")


class DatasetHandle:
    """Unified access to tabular data via Pandas (small) or DuckDB (large)."""

    def __init__(
        self,
        con: duckdb.DuckDBPyConnection,
        table: str = TABLE_NAME,
        df: Optional[pd.DataFrame] = None,
        is_duckdb_primary: bool = False,
        *,
        raw_table: Optional[str] = None,
        cached_row_count: Optional[int] = None,
        prepared_for_analysis: bool = False,
    ):
        self._con = con
        self._table = table
        self._df = df
        self._is_duckdb_primary = is_duckdb_primary
        self._raw_table = raw_table
        self._cached_row_count = cached_row_count
        self._prepared_for_analysis = prepared_for_analysis
        self._effective_mapping: Dict[str, str] = {}
        self._data_contract: Dict[str, object] = {}
        self._recipe_hash: Optional[str] = None
        self._source_fingerprint: Optional[str] = None
        self._contract_hash: Optional[str] = None
        self._dataset_version_id: Optional[str] = None
        self._cleaning_report: Dict[str, object] = {}
        self._summarize_df: Optional[pd.DataFrame] = None

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> "DatasetHandle":
        con = duckdb.connect()
        if df is None or df.empty:
            return cls(con=con, table=TABLE_NAME, df=df, is_duckdb_primary=False)
        if len(df) >= settings.DUCKDB_ROW_THRESHOLD:
            con.register(TABLE_NAME, df)
            return cls(
                con=con,
                table=TABLE_NAME,
                df=None,
                is_duckdb_primary=True,
                cached_row_count=len(df),
            )
        return cls(con=con, table=TABLE_NAME, df=df, is_duckdb_primary=False, cached_row_count=len(df))

    @classmethod
    def from_file_path(
        cls,
        path: str,
        file_name: str,
        target_cols: Optional[List[str]] = None,
        *,
        cleanup_path: bool = False,
    ) -> Optional["DatasetHandle"]:
        ext = file_name.rsplit(".", 1)[-1].lower()
        if ext not in ("csv", "parquet"):
            return None

        con = duckdb.connect()
        esc = _escape_path(path)
        try:
            if ext == "parquet":
                con.execute(f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM read_parquet('{esc}')")
            else:
                header_row = detect_header_row_from_path(path, file_name)
                con.execute(
                    f"CREATE TABLE {TABLE_NAME} AS "
                    f"SELECT * FROM read_csv_auto('{esc}', header=true, skip={int(header_row)})"
                )

            count = int(con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0])
            if target_cols:
                available = {r[0] for r in con.execute(f"DESCRIBE {TABLE_NAME}").fetchall()}
                valid = [c for c in target_cols if c in available]
                if valid:
                    quoted = ", ".join('"' + c.replace('"', '""') + '"' for c in valid)
                    con.execute(
                        f"CREATE TABLE {TABLE_NAME}_sel AS SELECT {quoted} FROM {TABLE_NAME}"
                    )
                    con.execute(f"DROP TABLE {TABLE_NAME}")
                    con.execute(f"ALTER TABLE {TABLE_NAME}_sel RENAME TO {TABLE_NAME}")

            if count >= settings.DUCKDB_ROW_THRESHOLD:
                return cls(
                    con=con,
                    table=TABLE_NAME,
                    is_duckdb_primary=True,
                    cached_row_count=count,
                )
            df = con.execute(f"SELECT * FROM {TABLE_NAME}").df()
            return cls.from_dataframe(df)
        except Exception as e:
            print(f"DatasetHandle.from_file_path failed for {file_name}: {e}")
            return None
        finally:
            if cleanup_path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass

    @classmethod
    def from_bytes(
        cls,
        file_bytes: bytes,
        file_name: str,
        target_cols: Optional[List[str]] = None,
    ) -> Optional["DatasetHandle"]:
        ext = file_name.rsplit(".", 1)[-1].lower()
        if ext in ("csv", "parquet"):
            suffix = f".{ext}"
            path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(file_bytes)
                    path = tmp.name
                return cls.from_file_path(path, file_name, target_cols, cleanup_path=True)
            except Exception as e:
                print(f"DatasetHandle.from_bytes failed for {file_name}: {e}")
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
                return None

        con = duckdb.connect()
        try:
            if ext in ("xlsx", "xls"):
                from app.services.large_data_ingest import ingest_excel_bytes

                return ingest_excel_bytes(file_bytes, target_cols)

            if ext == "json":
                from app.services.large_data_ingest import ingest_json_bytes

                return ingest_json_bytes(file_bytes, target_cols)

            return None
        except Exception as e:
            print(f"DatasetHandle.from_bytes failed for {file_name}: {e}")
            return None

    def invalidate_summarize_cache(self) -> None:
        self._summarize_df = None

    def summarize_df(self, *, refresh: bool = False) -> pd.DataFrame:
        if self._summarize_df is None or refresh:
            if self._df is not None:
                self._con.register(TABLE_NAME, self._df)
            self._summarize_df = self._con.execute(f"SUMMARIZE {self._table}").df()
        return self._summarize_df

    @property
    def is_large(self) -> bool:
        return self._is_duckdb_primary

    def row_count(self) -> int:
        if self._cached_row_count is not None:
            return self._cached_row_count
        if self._df is not None:
            self._cached_row_count = len(self._df)
            return self._cached_row_count
        count = int(self._con.execute(f"SELECT COUNT(*) FROM {self._table}").fetchone()[0])
        self._cached_row_count = count
        return count

    def column_names(self) -> List[str]:
        if self._df is not None:
            return list(self._df.columns)
        rows = self._con.execute(f"DESCRIBE {self._table}").fetchall()
        return [r[0] for r in rows]

    def to_pandas(self, limit: Optional[int] = None) -> pd.DataFrame:
        if self._df is not None:
            return self._df.head(limit) if limit else self._df.copy()
        query = f"SELECT * FROM {self._table}"
        if limit:
            query += f" LIMIT {int(limit)}"
        return self._con.execute(query).df()

    def profile_columns(self, summarize_df: Optional[pd.DataFrame] = None) -> str:
        if self._is_duckdb_primary or self._df is None:
            return self._profile_via_summarize(summarize_df)
        if self._df is not None:
            return build_column_profile(self._df)
        return self._profile_via_summarize(summarize_df)

    def _profile_via_summarize(self, summarize_df: Optional[pd.DataFrame] = None) -> str:
        try:
            summary = summarize_df if summarize_df is not None else self.summarize_df()
            lines: List[str] = []
            for _, row in summary.iterrows():
                col = row.get("column_name", "?")
                ctype = row.get("column_type", "?")
                null_pct = row.get("null_percentage", 0)
                min_v = row.get("min", "—")
                max_v = row.get("max", "—")
                avg_v = row.get("avg", "—")
                lines.append(
                    f"- {col} ({ctype}): null {float(null_pct):.1f}%, "
                    f"range [{min_v} – {max_v}], mean {avg_v}"
                )
            return "\n".join(lines)
        except Exception as e:
            print(f"DuckDB SUMMARIZE failed: {e}")
            sample = self.to_pandas(limit=min(self.row_count(), 50000))
            return build_column_profile(sample)

    def pandas_for_execution(self) -> pd.DataFrame:
        if self._is_duckdb_primary:
            raise ValueError("Dataset too large for Pandas execution; use DuckDB SQL path.")
        return self.to_pandas()

    def execute_select(self, sql: str, max_rows: Optional[int] = None) -> pd.DataFrame:
        cleaned = (sql or "").strip().rstrip(";")
        lower = cleaned.lower()
        if not (lower.startswith("select") or lower.startswith("with")):
            raise ValueError("Only SELECT queries are permitted.")
        if FORBIDDEN_SQL.search(lower):
            raise ValueError("Forbidden SQL keyword detected.")
        if self._df is not None:
            self._con.register(TABLE_NAME, self._df)
        cap = max_rows or int(settings.MAX_SQL_RESULT_ROWS)
        if not re.search(r"\blimit\s+\d+", lower):
            cleaned = f"{cleaned} LIMIT {cap}"
        result = self._con.execute(cleaned).df()
        if len(result) > cap:
            return result.head(cap)
        return result

    @classmethod
    def for_sql_execution(cls, handle: "DatasetHandle") -> "DatasetHandle":
        """Register dataset in DuckDB for question-aware SQL (all sizes)."""
        if handle.is_large:
            return handle
        df = handle.to_pandas()
        con = duckdb.connect()
        con.register(TABLE_NAME, df)
        return cls(
            con=con,
            table=TABLE_NAME,
            is_duckdb_primary=True,
            cached_row_count=len(df),
        )

    def _physical_source_table(self) -> str:
        return self._raw_table or self._table

    @staticmethod
    def _is_attached_source(table_ref: str) -> bool:
        """True when table_ref points at an ATTACH-ed catalog (e.g. persist_src.df)."""
        if not table_ref or "." not in table_ref:
            return False
        catalog = table_ref.split(".", 1)[0].strip('"').lower()
        return catalog not in ("main", "memory")

    def _materialize_attached_raw_table(self, qualified: str) -> str:
        """Copy ATTACH read-only source into a writable in-memory table for clean/mapping."""
        raw_name = f"{self._table}{RAW_TABLE_SUFFIX}"
        self._con.execute(f"DROP TABLE IF EXISTS {raw_name}")
        self._con.execute(f"CREATE TABLE {raw_name} AS SELECT * FROM {qualified}")
        try:
            self._con.execute(f"DROP VIEW IF EXISTS {self._table}")
        except Exception:
            pass
        self._raw_table = raw_name
        return raw_name

    def _ensure_raw_table(self) -> str:
        if self._raw_table:
            if self._is_attached_source(self._raw_table):
                return self._materialize_attached_raw_table(self._raw_table)
            return self._raw_table
        raw_name = f"{self._table}{RAW_TABLE_SUFFIX}"
        try:
            self._con.execute(f"ALTER TABLE {self._table} RENAME TO {raw_name}")
        except Exception:
            self._con.execute(f"DROP TABLE IF EXISTS {raw_name}")
            self._con.execute(f"CREATE TABLE {raw_name} AS SELECT * FROM {self._table}")
            try:
                self._con.execute(f"DROP VIEW IF EXISTS {self._table}")
            except Exception:
                pass
            try:
                self._con.execute(f"DROP TABLE IF EXISTS {self._table}")
            except Exception:
                pass
        self._raw_table = raw_name
        return raw_name

    def apply_standard_clean(
        self,
        column_mapping: Optional[Dict[str, str]] = None,
        cleaning_profile: str = "standard",
        cleaning_recipe: Optional[Dict[str, object]] = None,
    ) -> Tuple[List[str], "DatasetHandle"]:
        """Trim, dedupe, normalize empties, forward-fill merged cells, pre-parse dates."""
        from app.services.data_cleaning import clean_dataframe, clean_handle_duckdb

        if not self._is_duckdb_primary and self._df is not None:
            notes, df = clean_dataframe(
                self._df, column_mapping, cleaning_profile, cleaning_recipe
            )
            cleaned = DatasetHandle.from_dataframe(df)
            cleaned._cleaning_report = dict(df.attrs.get("cleaning_report") or {})
            return notes, cleaned
        return clean_handle_duckdb(
            self, column_mapping, cleaning_profile, cleaning_recipe
        )

    def prepare_for_analysis(
        self,
        column_mapping: Optional[Dict[str, str]] = None,
        cleaning_profile: str = "standard",
        cleaning_recipe: Optional[Dict[str, object]] = None,
    ) -> Tuple[List[str], "DatasetHandle"]:
        """Standard cleaning followed by semantic column mapping coercion."""
        from app.services.etl_pipeline import (
            effective_mapping_for_contract,
            normalize_data_contract,
            recipe_hash,
        )

        notes: List[str] = []
        recipe = cleaning_recipe if isinstance(cleaning_recipe, dict) else {}
        contract = normalize_data_contract(recipe.get("data_contract"))
        effective_mapping = effective_mapping_for_contract(column_mapping, contract)
        current_recipe_hash = str(recipe.get("recipe_hash") or "").strip() or (
            recipe_hash(recipe) if recipe else None
        )
        current_contract_hash = str(recipe.get("contract_hash") or "").strip() or (
            hashlib.sha256(
                json.dumps(contract, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            if contract
            else None
        )
        current_dataset_version_id = str(
            recipe.get("dataset_version_id")
            or recipe.get("data_setup_session_id")
            or ""
        ).strip() or None
        current_source_fingerprint = str(
            recipe.get("source_fingerprint") or self._source_fingerprint or ""
        ).strip() or None
        if recipe.get("materialized_prepared"):
            self._prepared_for_analysis = True
            self._effective_mapping = effective_mapping
            self._data_contract = contract
            self._recipe_hash = current_recipe_hash
            self._source_fingerprint = current_source_fingerprint
            self._contract_hash = current_contract_hash
            self._dataset_version_id = current_dataset_version_id
            return notes, self
        clean_notes, handle = self.apply_standard_clean(
            column_mapping, cleaning_profile, cleaning_recipe
        )
        notes.extend(clean_notes)
        map_notes, handle = handle.apply_mapping_clean(column_mapping or {})
        notes.extend(map_notes)
        contract_notes, handle = handle.apply_business_contract(contract, effective_mapping)
        notes.extend(contract_notes)
        if handle._cleaning_report:
            handle._cleaning_report.setdefault("mapping", {})
            handle._cleaning_report["mapping"]["notes"] = list(map_notes)
        handle._prepared_for_analysis = True
        handle._effective_mapping = effective_mapping
        handle._data_contract = contract
        handle._recipe_hash = current_recipe_hash
        handle._source_fingerprint = current_source_fingerprint
        handle._contract_hash = current_contract_hash
        handle._dataset_version_id = current_dataset_version_id
        return notes, handle

    def apply_business_contract(
        self,
        contract: Dict[str, object],
        effective_mapping: Dict[str, str],
    ) -> Tuple[List[str], "DatasetHandle"]:
        """Apply deterministic business rules approved in the Data Contract."""
        notes: List[str] = []
        if not contract or not contract.get("business_context_reviewed"):
            return notes, self

        role_to_column = {
            role: column for column, role in effective_mapping.items()
            if column in set(self.column_names())
        }
        status_column = role_to_column.get("status") or role_to_column.get("payment_status")
        revenue_column = role_to_column.get("sales")
        cancellation_policy = str(contract.get("cancellation_policy") or "include_all")
        cancelled_terms = ("cancelled", "canceled", "void", "ยกเลิก")
        return_terms = ("returned", "return", "refunded", "refund", "คืน")

        if not self._is_duckdb_primary and self._df is not None:
            work = self._df.copy()
            if status_column and status_column in work.columns and cancellation_policy != "include_all":
                status_text = work[status_column].fillna("").astype(str).str.casefold()
                cancelled = status_text.apply(lambda value: any(term in value for term in cancelled_terms))
                returned = status_text.apply(lambda value: any(term in value for term in return_terms))
                before = len(work)
                if cancellation_policy == "exclude_all":
                    work = work.loc[~(cancelled | returned)].copy()
                elif cancellation_policy == "exclude_cancelled_net_returns":
                    work = work.loc[~cancelled].copy()
                    if revenue_column and revenue_column in work.columns:
                        returned_kept = returned.reindex(work.index, fill_value=False)
                        values = pd.to_numeric(work[revenue_column], errors="coerce")
                        work.loc[returned_kept, revenue_column] = -values.loc[returned_kept].abs()
                removed = before - len(work)
                notes.append(f"Data Contract cancellation policy applied; {removed} rows excluded.")
            date_column = role_to_column.get("date") or role_to_column.get("timestamp")
            fiscal_month = str(contract.get("fiscal_year_start") or "01")
            if date_column and date_column in work.columns and fiscal_month.isdigit():
                month = max(1, min(12, int(fiscal_month)))
                parsed = pd.to_datetime(work[date_column], errors="coerce")
                work["__fiscal_year"] = parsed.dt.year + (parsed.dt.month >= month).astype("Int64") - (1 if month == 1 else 0)
                work["__fiscal_period"] = ((parsed.dt.month - month) % 12 + 1).astype("Int64")
            prepared = DatasetHandle.from_dataframe(work)
            prepared._cleaning_report = dict(self._cleaning_report or {})
            return notes, prepared

        if status_column and cancellation_policy != "include_all":
            raw = self._ensure_raw_table()
            status_q = _quote_ident(status_column)
            normalized_status = f"lower(coalesce(cast({status_q} as varchar), ''))"
            cancelled_sql = " OR ".join(
                f"contains({normalized_status}, '{term}')" for term in cancelled_terms
            )
            returned_sql = " OR ".join(
                f"contains({normalized_status}, '{term}')" for term in return_terms
            )
            before = self.row_count()
            if cancellation_policy == "exclude_all":
                self._con.execute(f"DELETE FROM {raw} WHERE ({cancelled_sql}) OR ({returned_sql})")
            elif cancellation_policy == "exclude_cancelled_net_returns":
                self._con.execute(f"DELETE FROM {raw} WHERE {cancelled_sql}")
                if revenue_column:
                    revenue_q = _quote_ident(revenue_column)
                    self._con.execute(
                        f"UPDATE {raw} SET {revenue_q} = -abs(try_cast({revenue_q} AS DOUBLE)) "
                        f"WHERE {returned_sql}"
                    )
            self._cached_row_count = None
            notes.append(
                f"Data Contract cancellation policy applied; {before - self.row_count()} rows excluded."
            )
        date_column = role_to_column.get("date") or role_to_column.get("timestamp")
        fiscal_month = str(contract.get("fiscal_year_start") or "01")
        if date_column and fiscal_month.isdigit():
            month = max(1, min(12, int(fiscal_month)))
            date_q = _quote_ident(date_column)
            raw = self._ensure_raw_table()
            self._con.execute("DROP TABLE IF EXISTS __contract_prepared")
            fiscal_year = (
                f"year(try_cast({date_q} AS TIMESTAMP)) + "
                f"CASE WHEN {month} = 1 THEN 0 "
                f"WHEN month(try_cast({date_q} AS TIMESTAMP)) >= {month} THEN 1 ELSE 0 END"
            )
            fiscal_period = (
                f"((month(try_cast({date_q} AS TIMESTAMP)) - {month} + 12) % 12) + 1"
            )
            self._con.execute(
                f"CREATE TABLE __contract_prepared AS SELECT *, "
                f"{fiscal_year}::INTEGER AS __fiscal_year, "
                f"{fiscal_period}::INTEGER AS __fiscal_period FROM {self._table}"
            )
            self._con.execute(f"DROP VIEW IF EXISTS {self._table}")
            self._con.execute(f"DROP TABLE IF EXISTS {raw}")
            self._con.execute(f"ALTER TABLE __contract_prepared RENAME TO {raw}")
            self._con.execute(f"CREATE VIEW {self._table} AS SELECT * FROM {raw}")
            self._raw_table = raw
            self.invalidate_summarize_cache()
        return notes, self

    def apply_mapping_clean(self, column_mapping: Dict[str, str]) -> Tuple[List[str], "DatasetHandle"]:
        """Validate mapping and expose cleaned columns via DuckDB view (no full table copy)."""
        notes: List[str] = []
        if not column_mapping:
            return notes, self

        # Semantic mapping must never imply projection. Unmapped source columns
        # remain available for drill-down, future remapping and lineage. Column
        # removal is an explicit ETL transformation, not a side effect of mapping.
        available_columns = self.column_names()
        available = set(available_columns)
        cols = [c for c in column_mapping if c in available]
        provenance_cols = [
            c for c in available
            if (c.endswith("__imputed") or c.endswith("__outlier"))
            and c.rsplit("__", 1)[0] in cols
        ]
        if not cols:
            return notes, self

        if not self._is_duckdb_primary and self._df is not None:
            work = self._df.copy()
            for col_name, mapped_name in column_mapping.items():
                if col_name not in work.columns:
                    continue
                val = (mapped_name or "").strip().lower()
                nulls = work[col_name].isnull().sum()
                if nulls:
                    notes.append(f"Column '{col_name}': {nulls} missing values detected.")
                if val in _NUMERIC_MAPPINGS:
                    from app.services.data_cleaning import strip_currency_text

                    original = work[col_name].copy()
                    stripped = work[col_name].map(strip_currency_text)
                    work[col_name] = pd.to_numeric(stripped, errors="coerce")
                    bad = original.notna() & work[col_name].isna()
                    if bad.any():
                        notes.append(
                            f"Column '{col_name}': {bad.sum()} non-numeric values converted to null; no zero values were fabricated."
                        )
            cleaned = DatasetHandle.from_dataframe(work)
            cleaned._cleaning_report = dict(self._cleaning_report or {})
            return notes, cleaned

        source = self._physical_source_table()
        agg_parts: List[str] = []
        for col_name in cols:
            q = _quote_ident(col_name)
            agg_parts.append(f"SUM(CASE WHEN {q} IS NULL THEN 1 ELSE 0 END)")
            mapped = (column_mapping.get(col_name) or "").strip().lower()
            if mapped in _NUMERIC_MAPPINGS:
                agg_parts.append(
                    f"SUM(CASE WHEN {q} IS NOT NULL AND try_cast({q} AS DOUBLE) IS NULL THEN 1 ELSE 0 END)"
                )

        try:
            agg_row = self._con.execute(
                f"SELECT {', '.join(agg_parts)} FROM {source}"
            ).fetchone()
            idx = 0
            for col_name in cols:
                nulls = int(agg_row[idx] or 0)
                idx += 1
                if nulls:
                    notes.append(f"Column '{col_name}': {nulls} missing values detected.")
                mapped = (column_mapping.get(col_name) or "").strip().lower()
                if mapped in _NUMERIC_MAPPINGS:
                    bad = int(agg_row[idx] or 0)
                    idx += 1
                    if bad:
                        notes.append(
                            f"Column '{col_name}': {bad} non-numeric values converted to null; no zero values were fabricated."
                        )
        except Exception as e:
            print(f"Mapping validation aggregate failed: {e}")

        select_exprs: List[str] = []
        for col_name in available_columns:
            q = _quote_ident(col_name)
            mapped = (column_mapping.get(col_name) or "").strip().lower()
            if mapped in _NUMERIC_MAPPINGS:
                stripped = (
                    f"REGEXP_REPLACE(REGEXP_REPLACE(CAST({q} AS VARCHAR), "
                    f"'[฿$€£¥₩₹]', ''), ',', '')"
                )
                select_exprs.append(f"try_cast({stripped} AS DOUBLE) AS {q}")
            else:
                select_exprs.append(q)
        raw_table = self._ensure_raw_table()
        try:
            self._con.execute(f"DROP VIEW IF EXISTS {self._table}")
        except Exception:
            pass
        self._con.execute(
            f"CREATE VIEW {self._table} AS SELECT {', '.join(select_exprs)} FROM {raw_table}"
        )
        self.invalidate_summarize_cache()
        return notes, self

    def infer_roles_from_sample(
        self, column_mapping: Optional[Dict[str, str]] = None, sample_size: int = 5000,
    ) -> Dict[str, str]:
        from app.services.domain_analytics import infer_semantic_roles

        sample = self.to_pandas(limit=min(sample_size, self.row_count()))
        return infer_semantic_roles(sample, column_mapping or {})

    def duckdb_summarize_stats(self, summarize_df: Optional[pd.DataFrame] = None) -> List[str]:
        lines = [f"=== Dataset Overview ({self.row_count():,} rows, DuckDB) ==="]
        try:
            summary = summarize_df if summarize_df is not None else self.summarize_df()
            for _, row in summary.iterrows():
                ctype = str(row.get("column_type", "")).upper()
                col = row["column_name"]
                if "INT" in ctype or "DOUBLE" in ctype or "FLOAT" in ctype or "DECIMAL" in ctype:
                    lines.append(
                        f"- {col}: sum={row.get('sum', '—')}, avg={row.get('avg', '—')}, "
                        f"min={row.get('min', '—')}, max={row.get('max', '—')}"
                    )
        except Exception as e:
            lines.append(f"- DuckDB summarize error: {e}")
        return lines


def open_persisted_duckdb_handle(
    path: str,
    *,
    is_duckdb_primary: Optional[bool] = None,
) -> Optional[DatasetHandle]:
    """
    Open a on-disk DuckDB cache read-only via ATTACH into a writable in-memory connection.

    Avoids opening the file directly in read-only mode. The attached catalog is read-only;
    `_ensure_raw_table()` copies into a writable in-memory table before clean/mapping mutations.
    """
    if not path or not os.path.exists(path):
        return None
    try:
        mem_con = duckdb.connect()
        esc = _escape_path(os.path.abspath(path))
        mem_con.execute(f"ATTACH '{esc}' AS persist_src (READ_ONLY)")
        qualified = f"persist_src.{TABLE_NAME}"
        count = int(mem_con.execute(f"SELECT COUNT(*) FROM {qualified}").fetchone()[0])
        mem_con.execute(f"CREATE VIEW {TABLE_NAME} AS SELECT * FROM {qualified}")
        primary = (
            is_duckdb_primary
            if is_duckdb_primary is not None
            else count >= settings.DUCKDB_ROW_THRESHOLD
        )
        return DatasetHandle(
            con=mem_con,
            table=TABLE_NAME,
            is_duckdb_primary=primary,
            cached_row_count=count,
            raw_table=qualified,
        )
    except Exception as e:
        print(f"open_persisted_duckdb_handle failed ({path}): {e}")
        return None


def as_handle(data: Union[pd.DataFrame, DatasetHandle]) -> DatasetHandle:
    if isinstance(data, DatasetHandle):
        return data
    return DatasetHandle.from_dataframe(data)
