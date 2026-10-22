from __future__ import annotations

import asyncio
import io
import json
import re
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Union

import openai
import pandas as pd
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.pipeline_log import log_pipeline_event
from app.core.supabase import get_supabase_client
from app.schemas.chat import ChatRequest, ChatResponse, Message
from app.services.agent_session_store import AgentPauseResult, load_df_from_session
from app.services.ai_logic import PromptManager
from app.services.analysis_agent import load_session_for_resume, run_autonomous_agent_loop
from app.services.analytics_cache import (
    get_question_result,
    question_cache_key,
    set_question_result,
)
from app.services.column_profile import build_column_profile
from app.services.data_context import build_dataset_metadata, metadata_from_handle
from app.services.dataset_engine import DatasetHandle, as_handle
from app.services.domain_analytics import (
    column_series,
    compute_domain_kpis,
    infer_dataset_type,
    infer_semantic_roles,
)
from app.services.json_structure import flatten_json_to_records, summarize_json_structure
from app.services.large_data_ingest import ingest_json_value
from app.services.chat.llm_client import LlmClient
from app.services.chat.pipeline import (
    emit_status,
    engine_detail,
    inject_insight_into_file_content,
    question_hint,
    should_cache_analytics,
)
from app.services.question_analytics import format_specific_insight, merge_into_analytics
from app.services.sql_execution import (
    build_db_url,
    build_select_all_query,
    create_db_engine,
    execute_select_to_handle,
    list_db_tables,
    validate_select_sql,
    validate_table_name,
)
from app.services.storage_download import FileAttachmentError, download_business_data_file


class PandasAnalyticsEngine:
    def calculate_for_handle(
        self,
        handle: DatasetHandle,
        column_mapping: Dict[str, str],
        user_id: Optional[str] = None,
        file_attachment_name: Optional[str] = None,
        connection_id: Optional[str] = None,
        cleaning_profile: str = "standard",
    ) -> Dict[str, Any]:
        from app.services.analytics_service import calculate_analytics_for_handle

        return calculate_analytics_for_handle(
            handle,
            column_mapping,
            user_id=user_id,
            file_attachment_name=file_attachment_name,
            connection_id=connection_id,
            cleaning_profile=cleaning_profile,
            pandas_calculator=self.calculate,
        )

    @staticmethod
    def _rename_columns_to_roles(df: pd.DataFrame, role_to_col: Dict[str, str]) -> pd.DataFrame:
        """Rename mapped columns to role names without creating duplicate column labels."""
        calc_df = df.copy()
        rename_map: Dict[str, str] = {}
        used_targets = set(calc_df.columns)
        for role, orig_col in role_to_col.items():
            if orig_col not in calc_df.columns:
                continue
            target = role
            if target in used_targets and target != orig_col:
                target = f"{role}__role"
                suffix = 2
                while target in used_targets:
                    target = f"{role}__role_{suffix}"
                    suffix += 1
            rename_map[orig_col] = target
            used_targets.add(target)
        return calc_df.rename(columns=rename_map)

    @staticmethod
    def _numeric_series(df: pd.DataFrame, col: str) -> pd.Series:
        series = column_series(df, col)
        if series is None:
            return pd.Series(dtype=float)
        return pd.to_numeric(series, errors="coerce")

    @staticmethod
    def _monthly_resample_sum(df: pd.DataFrame, time_col: str, value_col: str) -> Optional[pd.Series]:
        """Sum by calendar month; returns None if dates are not parseable for resample."""
        if time_col not in df.columns or value_col not in df.columns:
            return None
        time_series = column_series(df, time_col)
        value_series = column_series(df, value_col)
        if time_series is None or value_series is None:
            return None
        work = pd.DataFrame({time_col: time_series, value_col: value_series})
        work[time_col] = pd.to_datetime(work[time_col], errors="coerce")
        work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
        work = work.dropna(subset=[time_col, value_col])
        if len(work) < 2:
            return None
        indexed = work.set_index(time_col)
        if not isinstance(indexed.index, pd.DatetimeIndex):
            return None
        try:
            return indexed[value_col].resample("MS").sum()
        except Exception:
            return None

    def calculate(self, df: pd.DataFrame, column_mapping: Dict[str, str]) -> Dict[str, Any]:
        """
        Layer 8: Analytics Engine - คำนวณ Metrics พื้นฐานด้วย Python (Pandas)
        วิเคราะห์คอลัมน์และข้อมูลทั้งหมดอย่างเป็นระบบ ยืดหยุ่น ไดนามิก เพื่อค้นหา Insights ทุกแง่มุมที่เป็นไปได้
        """
        analytics = []
        role_to_col: Dict[str, str] = infer_semantic_roles(df, column_mapping)
        try:
            calc_df = self._rename_columns_to_roles(df, role_to_col)
            cols = list(dict.fromkeys(calc_df.columns))

            # Ensure 'date' or 'timestamp' column is in datetime format
            time_col = None
            if 'date' in cols:
                time_col = 'date'
            elif 'timestamp' in cols:
                time_col = 'timestamp'

            if time_col:
                calc_df[time_col] = pd.to_datetime(column_series(calc_df, time_col), errors='coerce')
                calc_df = calc_df.dropna(subset=[time_col]).sort_values(time_col)
                if not pd.api.types.is_datetime64_any_dtype(calc_df[time_col]):
                    time_col = None

            # 1. ค้นหาคอลัมน์ที่เป็นตัวเลข (Numeric) ทั้งหมด
            numeric_roles = []
            for col in cols:
                # ลองแปลงเป็นตัวเลข ดูว่าอัตราส่วนแปลงผ่านสูงกว่า 70% หรือไม่
                series_numeric = self._numeric_series(calc_df, col)
                raw_series = column_series(calc_df, col)
                non_null_count = raw_series.dropna().shape[0] if raw_series is not None else 0
                valid_num_count = series_numeric.dropna().shape[0]
                if non_null_count > 0 and (valid_num_count / non_null_count) >= 0.7:
                    numeric_roles.append(col)

            # 2. คำนวณสถิติพื้นฐานของคอลัมน์ตัวเลขทั้งหมด
            if numeric_roles:
                analytics.append("=== Summary Statistics ===")
                for col in numeric_roles:
                    num_series = self._numeric_series(calc_df, col)
                    total_sum = num_series.sum()
                    avg_val = num_series.mean()
                    min_val = num_series.min()
                    max_val = num_series.max()
                    missing_pct = num_series.isnull().mean() * 100

                    stat_line = f"- **{col.upper()}**: Sum: {total_sum:,.2f} | Avg: {avg_val:,.2f} | Range: [{min_val:,.2f} to {max_val:,.2f}]"
                    if missing_pct > 0:
                        stat_line += f" (Missing: {missing_pct:.1f}%)"
                    analytics.append(stat_line)

            # 3. การคำนวณทางการเงินร่วมระหว่างยอดขายและต้นทุน (ถ้ามี)
            if 'cost' in numeric_roles and 'sales' in numeric_roles:
                sales_val = self._numeric_series(calc_df, 'sales').fillna(0).sum()
                cost_val = self._numeric_series(calc_df, 'cost').fillna(0).sum()
                profit_val = sales_val - cost_val
                margin_pct = (profit_val / sales_val * 100) if sales_val != 0 else 0
                analytics.append(f"- **FINANCIAL OVERVIEW**: Gross Profit: {profit_val:,.2f} | Profit Margin: {margin_pct:.2f}%")

            # 4. การวิเคราะห์แนวโน้มเวลาแบบไดนามิก (Dynamic Time-Series Analytics)
            if time_col and len(calc_df) > 1 and numeric_roles:
                analytics.append("\n=== Time-Series Trends & Monthly Breakdowns ===")
                for col in numeric_roles:
                    monthly_metric = self._monthly_resample_sum(calc_df, time_col, col)
                    if monthly_metric is not None and not monthly_metric.empty:
                        analytics.append(f"- **{col.upper()} Monthly Sums**:")
                        for m_date, val in monthly_metric.items():
                            analytics.append(f"  * {m_date.strftime('%Y-%m')}: {val:,.2f}")

                        if len(monthly_metric) > 1:
                            mom_growth = monthly_metric.pct_change() * 100
                            last_growth = mom_growth.iloc[-1]
                            if not pd.isna(last_growth):
                                second_last_month = monthly_metric.index[-2].strftime('%Y-%m')
                                last_month = monthly_metric.index[-1].strftime('%Y-%m')
                                direction = "increased" if last_growth > 0 else "decreased"
                                analytics.append(f"  * MoM Growth ({second_last_month} to {last_month}): {last_growth:+.2f}% ({direction})")

            # 5. ค้นหามิติการจำแนกประเภท (Categorical Dimensions)
            categorical_roles = []
            for col in cols:
                if col not in numeric_roles and col not in ['date', 'timestamp']:
                    # คอลัมน์ที่จำนวนค่าเฉพาะตัวไม่กว้างจนเกินไป
                    cat_series = column_series(calc_df, col)
                    if cat_series is None:
                        continue
                    unique_count = cat_series.dropna().nunique()
                    if 1 < unique_count < 100:
                        categorical_roles.append(col)

            # 6. การเปรียบเทียบมิติข้อมูลแบบหลายมิติ (Multi-dimensional Groupings)
            if categorical_roles and numeric_roles:
                analytics.append("\n=== Categorical Breakdowns & Top Performers ===")
                for cat_col in categorical_roles:
                    for num_col in numeric_roles:
                        cat_data = column_series(calc_df, cat_col)
                        num_data = self._numeric_series(calc_df, num_col)
                        if cat_data is None:
                            continue
                        mask = cat_data.notna() & num_data.notna()
                        if mask.sum() > 2:
                            grouped = num_data[mask].groupby(cat_data[mask]).sum()
                            if not grouped.empty:
                                top_entity = grouped.idxmax()
                                top_value = grouped.max()
                                total_metric = grouped.sum()
                                contrib_pct = (top_value / total_metric * 100) if total_metric != 0 else 0
                                analytics.append(f"- **Top {cat_col.upper()}** (by {num_col.upper()}): **{top_entity}** with {top_value:,.2f} ({contrib_pct:.1f}% of total)")

            # 7. ค้นหาความสัมพันธ์ระหว่างมิติตัวเลข (Pairwise Correlation Analysis)
            if len(numeric_roles) >= 2:
                analytics.append("\n=== Statistically Mapped Relationships ===")
                unique_numeric = list(dict.fromkeys(numeric_roles))
                numeric_parts = [self._numeric_series(calc_df, c) for c in unique_numeric]
                numeric_df = pd.concat(numeric_parts, axis=1)
                numeric_df.columns = unique_numeric
                corr_matrix = numeric_df.corr()
                found_correlation = False
                for i in range(len(unique_numeric)):
                    for j in range(i + 1, len(unique_numeric)):
                        col1, col2 = unique_numeric[i], unique_numeric[j]
                        r_val = corr_matrix.loc[col1, col2]
                        if not pd.isna(r_val) and abs(r_val) > 0.3:
                            found_correlation = True
                            relationship = "positive/direct" if r_val > 0 else "negative/inverse"
                            strength = "strong" if abs(r_val) > 0.7 else "moderate"
                            analytics.append(f"- Mapped relationship between **{col1.upper()}** and **{col2.upper()}** is {strength} {relationship} (r = {r_val:+.2f})")
                if not found_correlation:
                    analytics.append("- No statistically moderate or strong linear relationships detected between variables.")

            # 8. ค้นหาความผิดปกติของข้อมูล (Dynamic Z-Score Outlier Checking)
            outlier_notes = []
            for col in numeric_roles:
                num_series = self._numeric_series(calc_df, col).dropna()
                if len(num_series) > 10:
                    mean_val = num_series.mean()
                    std_val = num_series.std()
                    if std_val > 0:
                        z_scores = (num_series - mean_val) / std_val
                        outlier_count = int((abs(z_scores) > 2.8).sum())
                        if outlier_count > 0:
                            outlier_notes.append(
                                f"- Detected {outlier_count} anomalous data points in **{col.upper()}** "
                                f"(exceeding 2.8 standard deviations)"
                            )
            if outlier_notes:
                analytics.append("\n=== Data Anomaly Warnings ===")
                analytics.extend(outlier_notes)

            domain_kpis = compute_domain_kpis(df, role_to_col)
            if domain_kpis:
                analytics.append("\n=== Domain-Specific KPIs ===")
                analytics.extend(domain_kpis)

        except Exception as e:
            print(f"Universal Basic Analytics Error: {e}")
            return {"formatted_notes": "Note: Universal dynamic analytics computed partially due to column formatting."}

        suggested_type = infer_dataset_type(role_to_col) if role_to_col else "general_business_data"
        column_profile = build_column_profile(df)
        return {
            "formatted_notes": "\n".join(analytics) if analytics else "No standard metrics calculated.",
            "raw_metrics": analytics,
            "detected_roles": role_to_col,
            "suggested_dataset_type": suggested_type,
            "column_profile": column_profile,
        }
