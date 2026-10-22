from __future__ import annotations

import asyncio
import io
import json
import re
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Union

import numpy as np
import openai
import pandas as pd
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.pipeline_log import log_pipeline_event
from app.core.supabase import get_supabase_client
from app.schemas.chat import ChatRequest, ChatResponse, Message
from app.services.agent_session_store import AgentPauseResult, load_handle_from_session, load_df_from_session
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
from app.services.sql_execution import (
    build_db_url,
    build_select_all_query,
    create_db_engine,
    execute_select_to_handle,
    is_supported_db_provider,
    list_db_tables,
    validate_select_sql,
    validate_table_name,
)
from app.core.parser import detect_header_row_from_bytes, select_excel_sheet_from_bytes
from app.services.dataset_loader import load_handle_from_storage
from app.services.storage_download import FileAttachmentError


from app.services.chat.pandas_analytics import PandasAnalyticsEngine


class DataIngestService:

    def __init__(self, llm: LlmClient, analytics: "PandasAnalyticsEngine") -> None:
        self.llm = llm
        self.analytics = analytics

    async def _emit_status(
        self,
        on_status: Optional[Callable[[str, Optional[Dict[str, Any]]], Awaitable[None]]],
        stage: str,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        await emit_status(on_status, stage, detail)

    @staticmethod
    def _engine_detail(handle: DatasetHandle) -> Dict[str, Any]:
        return engine_detail(handle)

    async def _safe_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int] = None,
    ):
        return await self.llm.safe_chat_completion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _bytes_to_dataframe(
        self,
        file_bytes: bytes,
        file_name: str,
        column_mapping: Optional[Dict[str, str]] = None,
    ) -> Optional[pd.DataFrame]:
        mapping = column_mapping if column_mapping and isinstance(column_mapping, dict) else None
        target_cols = list(mapping.keys()) if mapping else None
        ext = file_name.split(".")[-1].lower()

        if ext not in ["csv", "xlsx", "xls", "parquet", "json"]:
            return None

        try:
            if ext == "csv":
                header_row = detect_header_row_from_bytes(file_bytes, file_name)
                if target_cols:
                    header_df = pd.read_csv(
                        io.BytesIO(file_bytes), skiprows=header_row, nrows=0
                    )
                    valid_cols = [c for c in target_cols if c in header_df.columns]
                    return pd.read_csv(
                        io.BytesIO(file_bytes),
                        skiprows=header_row,
                        usecols=valid_cols if valid_cols else None,
                    )
                return pd.read_csv(io.BytesIO(file_bytes), skiprows=header_row)
            if ext in ["xlsx", "xls"]:
                sheet_name = select_excel_sheet_from_bytes(file_bytes)
                header_row = detect_header_row_from_bytes(file_bytes, file_name)
                frame = pd.read_excel(
                    io.BytesIO(file_bytes),
                    sheet_name=sheet_name,
                    header=header_row,
                )
                if target_cols:
                    valid_cols = [c for c in target_cols if c in frame.columns]
                    if valid_cols:
                        return frame[valid_cols]
                return frame
            if ext == "parquet":
                if target_cols:
                    import pyarrow.parquet as pq
                    pf = pq.ParquetFile(io.BytesIO(file_bytes))
                    valid_cols = [c for c in target_cols if c in pf.schema.names]
                    return pd.read_parquet(
                        io.BytesIO(file_bytes),
                        columns=valid_cols if valid_cols else None,
                    )
                return pd.read_parquet(io.BytesIO(file_bytes))
            data = json.loads(file_bytes)
            records = flatten_json_to_records(data)
            if records:
                return pd.DataFrame(records)
        except Exception as e:
            print(f"bytes_to_dataframe failed for {file_name}: {e}")
        return None


    def _execute_sql_query(self, connection_id: str, user_id: str, sql_query: str) -> Optional[DatasetHandle]:
        from app.services.connection_secrets import hydrate_database_connection
        try:
            supabase = get_supabase_client()
            res = supabase.from_("database_connections").select("*").eq("id", connection_id).eq("user_id", user_id).single().execute()
            if not res.data:
                return None
            conn = hydrate_database_connection(res.data)
            provider = conn.get("provider")
            if not is_supported_db_provider(provider):
                return None
            db_url = build_db_url(
                provider,
                conn.get("username"),
                conn.get("password_encrypted"),
                conn.get("host"),
                conn.get("port"),
                conn.get("db_name"),
            )
            engine = create_db_engine(db_url, provider)
            handle = execute_select_to_handle(engine, sql_query, provider)
            return None if handle.row_count() == 0 else handle
        except Exception as e:
            print(f"SQL reload for agent session failed: {e}")
            return None


    def _fetch_api_handle(self, connection_id: str, user_id: str) -> Optional[DatasetHandle]:
        from app.services.connection_secrets import hydrate_api_connection
        try:
            supabase = get_supabase_client()
            res = supabase.from_("api_connections").select("*").eq("id", connection_id).eq("user_id", user_id).single().execute()
            if not res.data:
                return None
            from app.services.large_data_ingest import ingest_api_connection

            handle = ingest_api_connection(hydrate_api_connection(res.data))
            return handle
        except Exception as e:
            print(f"API reload for agent session failed: {e}")
        return None


    async def reload_dataframe_for_session(self, session: Any, user_id: str) -> Optional[DatasetHandle]:
        handle = load_handle_from_session(session)
        if handle is not None:
            return handle

        df = load_df_from_session(session)
        if df is not None and not df.empty:
            return DatasetHandle.from_dataframe(df)

        conn_type = (session.connection_type or "").lower()
        if session.connection_id and conn_type == "sql" and session.sql_query:
            handle = await asyncio.to_thread(
                self._execute_sql_query,
                session.connection_id,
                user_id,
                session.sql_query,
            )
            if handle is not None:
                return handle

        if session.connection_id and conn_type == "api":
            handle = await asyncio.to_thread(self._fetch_api_handle, session.connection_id, user_id)
            if handle is not None:
                return handle

        file_name = session.file_attachment_name
        if file_name and not file_name.startswith("database_connection_"):
            try:
                target_cols = list(session.column_mapping.keys()) if session.column_mapping else None
                handle = await asyncio.to_thread(
                    load_handle_from_storage,
                    user_id,
                    file_name,
                    target_cols,
                )
                if handle is not None:
                    return handle
            except Exception as e:
                print(f"File reload for agent session failed: {e}")

        return None


    @staticmethod
    def parse_connection_mention(
        content: str,
        db_connections: List[Dict[str, Any]],
        api_connections: List[Dict[str, Any]],
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Parse @connection or @connection-table from message text."""
        text = (content or "").strip()
        if "@" not in text:
            return None, None, None

        candidates: List[tuple[str, str, str]] = []
        for row in db_connections:
            candidates.append((row.get("name", ""), row.get("id"), "sql"))
        for row in api_connections:
            candidates.append((row.get("name", ""), row.get("id"), "api"))
        candidates = [c for c in candidates if c[0]]
        candidates.sort(key=lambda c: len(c[0]), reverse=True)

        for name, conn_id, conn_type in candidates:
            prefix = f"@{name}"
            idx = text.find(prefix)
            if idx == -1:
                continue
            after = text[idx + len(prefix):]
            sql_table = None
            if after.startswith("-"):
                match = re.match(r"^([a-zA-Z0-9_.]+)", after[1:])
                if match:
                    sql_table = match.group(1)
            return conn_id, conn_type, sql_table
        return None, None, None


    async def handle_sql_connection(
        self,
        connection_id: str,
        user_id: str,
        user_question: str,
        model: str,
        on_status: Optional[Callable[[str, Optional[Dict[str, Any]]], Awaitable[None]]] = None,
        column_mapping: Optional[Dict[str, str]] = None,
        sql_table: Optional[str] = None,
        cleaning_profile: str = "standard",
    ) -> tuple[str, Optional[Dict[str, Any]], Optional[str], str, Optional[DatasetHandle]]:
        """
        เชื่อมต่อฐานข้อมูลภายนอกแบบสด ดึง Schema ส่งให้ AI เขียน SELECT แล้วนำมารันจริงโดยไม่ต้องบันทึกไฟล์
        """
        from app.services.connection_secrets import hydrate_database_connection

        conn_name = "SQL_DB"
        try:
            supabase = get_supabase_client()
            res = supabase.from_("database_connections").select("*").eq("id", connection_id).eq("user_id", user_id).single().execute()
            if not res.data:
                return "Error: Database connection not found.", None, None, conn_name, None

            conn = hydrate_database_connection(res.data)
            provider = conn.get("provider")
            host = conn.get("host")
            port = conn.get("port")
            db_name = conn.get("db_name")
            username = conn.get("username")
            password = conn.get("password_encrypted")
            conn_name = conn.get("name", "SQL_DB")

            if not is_supported_db_provider(provider):
                return f"Error: Unsupported database provider: {provider}", None, None, conn_name, None

            db_url = build_db_url(provider, username, password, host, port, db_name)

            from sqlalchemy import inspect

            engine = create_db_engine(db_url, provider)
            sql_table_clean = (sql_table or "").strip() or None

            if sql_table_clean:
                ok_tbl, tbl_err = validate_table_name(sql_table_clean)
                if not ok_tbl:
                    return f"Error: {tbl_err}", None, None, conn_name, None
                try:
                    allowed_tables = list_db_tables(engine, provider)
                except Exception as e:
                    return f"Error connecting to database: {str(e)}", None, None, conn_name, None
                if sql_table_clean not in allowed_tables:
                    return (
                        f"Error: Table '{sql_table_clean}' not found in database '{conn_name}'.",
                        None,
                        None,
                        conn_name,
                        None,
                    )
                sql_query = build_select_all_query(sql_table_clean)
                try:
                    handle = execute_select_to_handle(engine, sql_query, provider)
                except Exception as e:
                    return f"Error executing table query ({sql_query}): {str(e)}", None, None, conn_name, None
                if handle.row_count() == 0:
                    return (
                        f"The table '{sql_table_clean}' returned 0 rows.\nSQL Executed: {sql_query}",
                        None,
                        sql_query,
                        conn_name,
                        None,
                    )
                validation_notes, handle = handle.prepare_for_analysis(column_mapping, cleaning_profile)
                validation_summary = "\n".join(validation_notes) if validation_notes else ""
                if on_status:
                    await self._emit_status(on_status, "merging", self._engine_detail(handle))
                    await self._emit_status(
                        on_status,
                        "analytics",
                        {**self._engine_detail(handle), "action": "compute_stats"},
                    )
                analytics_results = self.analytics.calculate_for_handle(
                    handle,
                    column_mapping or {},
                    user_id=user_id,
                    connection_id=connection_id,
                    cleaning_profile=cleaning_profile,
                )
                if on_status and analytics_results.get("cleaning_report"):
                    await self._emit_status(
                        on_status,
                        "cleaning_report",
                        {
                            "report": analytics_results.get("cleaning_report"),
                            "data_quality_score": analytics_results.get("data_quality_score"),
                        },
                    )
                file_content = metadata_from_handle(
                    handle,
                    quality_notes=validation_summary or None,
                    sql_executed=sql_query,
                    extra_notes=f"Source table: {sql_table_clean}",
                )
                return file_content, analytics_results, sql_query, conn_name, handle

            schema_info = []
            try:
                with engine.connect():
                    inspector = inspect(engine)
                    tables = inspector.get_table_names()
                    if not tables:
                        return "Warning: The database contains no tables.", None, None, conn_name, None

                    # จำกัดการดึงข้อมูล 10 ตารางเพื่อประหยัด Token
                    for table in tables[:10]:
                        cols = inspector.get_columns(table)
                        col_desc = [f"{c['name']} ({str(c['type'])})" for c in cols]
                        schema_info.append(f"Table: {table}\nColumns: {', '.join(col_desc)}")
            except Exception as e:
                return f"Error connecting to database: {str(e)}", None, None, conn_name, None

            schema_str = "\n\n".join(schema_info)

            # 3. ส่งคำสั่งให้ AI สร้าง SQL SELECT Query
            prompt = (
                f"You are a Text-to-SQL assistant. Below is the SQL database schema:\n"
                f"=== DATABASE SCHEMA ===\n{schema_str}\n\n"
                f"Based on the user's question: \"{user_question}\", write a single valid SQL SELECT query to retrieve the answer.\n"
                f"Rules:\n"
                f"1. Respond ONLY with a valid SQL SELECT query inside a ```sql ... ``` block.\n"
                f"2. Only write SELECT statements. Do NOT write INSERT, UPDATE, DELETE, or any modifying statements.\n"
                f"3. Limit the results (e.g. LIMIT {settings.SQL_SYNC_ROW_LIMIT}) to keep memory safe.\n"
            )

            response = await self._safe_chat_completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=300
            )
            ai_sql_response = response.choices[0].message.content or ""

            # ดึงคำสั่ง SQL ออกจาก Code Block
            sql_match = re.search(r"```sql\s*([\s\S]*?)\s*```", ai_sql_response, re.IGNORECASE)
            sql_query = sql_match.group(1).strip() if sql_match else ai_sql_response.strip()

            ok, err = validate_select_sql(sql_query)
            if not ok:
                return f"Error: {err}. SQL proposed: {sql_query}", None, None, conn_name, None

            try:
                handle = execute_select_to_handle(engine, sql_query, provider)
            except Exception as e:
                return f"Error executing generated SQL query ({sql_query}): {str(e)}", None, None, conn_name, None

            if handle.row_count() == 0:
                return f"The query executed successfully but returned 0 rows.\nSQL Executed: {sql_query}", None, sql_query, conn_name, None

            validation_notes, handle = handle.prepare_for_analysis(column_mapping, cleaning_profile)
            validation_summary = "\n".join(validation_notes) if validation_notes else ""

            if on_status:
                await self._emit_status(on_status, "merging", self._engine_detail(handle))
                await self._emit_status(
                    on_status,
                    "analytics",
                    {**self._engine_detail(handle), "action": "compute_stats"},
                )
            analytics_results = self.analytics.calculate_for_handle(
                handle,
                column_mapping or {},
                user_id=user_id,
                connection_id=connection_id,
                cleaning_profile=cleaning_profile,
            )
            if on_status and analytics_results.get("cleaning_report"):
                await self._emit_status(
                    on_status,
                    "cleaning_report",
                    {
                        "report": analytics_results.get("cleaning_report"),
                        "data_quality_score": analytics_results.get("data_quality_score"),
                    },
                )
            file_content = metadata_from_handle(
                handle,
                quality_notes=validation_summary or None,
                sql_executed=sql_query,
            )
            return file_content, analytics_results, sql_query, conn_name, handle
        except Exception as e:
            return f"Error: Connection to database '{conn_name}' failed. Details: {str(e)}", None, None, conn_name, None


    async def handle_api_connection(
        self,
        connection_id: str,
        user_id: str,
        user_question: str,
        model: str,
        on_status: Optional[Callable[[str, Optional[Dict[str, Any]]], Awaitable[None]]] = None,
        column_mapping: Optional[Dict[str, str]] = None,
        cleaning_profile: str = "standard",
    ) -> tuple[str, Optional[Dict[str, Any]], Optional[DatasetHandle]]:
        """
        เชื่อมต่อ API ภายนอก ดึงข้อมูลสดมาแปลงเป็น DataFrame เพื่อวิเคราะห์ก่อนส่งต่อ AI
        """
        from app.services.connection_secrets import hydrate_api_connection

        try:
            supabase = get_supabase_client()
            res = supabase.from_("api_connections").select("*").eq("id", connection_id).eq("user_id", user_id).single().execute()
            if not res.data:
                return "Error: API connection not found.", None, None

            conn = hydrate_api_connection(res.data)
            conn_name = conn.get("name", "API_Conn")

            from app.services.large_data_ingest import ingest_api_connection

            try:
                handle = ingest_api_connection(conn)
            except Exception as e:
                return f"Error fetching API: {str(e)}", None, None

            if handle is not None:
                validation_notes, handle = handle.prepare_for_analysis(column_mapping, cleaning_profile)
                validation_summary = "\n".join(validation_notes) if validation_notes else ""
                if on_status:
                    await self._emit_status(on_status, "merging", self._engine_detail(handle))
                    await self._emit_status(
                        on_status,
                        "analytics",
                        {**self._engine_detail(handle), "action": "compute_stats"},
                    )
                analytics_results = self.analytics.calculate_for_handle(
                    handle,
                    column_mapping or {},
                    user_id=user_id,
                    connection_id=connection_id,
                    cleaning_profile=cleaning_profile,
                )
                if on_status and analytics_results.get("cleaning_report"):
                    await self._emit_status(
                        on_status,
                        "cleaning_report",
                        {
                            "report": analytics_results.get("cleaning_report"),
                            "data_quality_score": analytics_results.get("data_quality_score"),
                        },
                    )
                file_content = metadata_from_handle(
                    handle,
                    quality_notes=validation_summary or None,
                    extra_notes=f"Live API connection: {conn_name}",
                )
                return file_content, analytics_results, handle
            else:
                from app.services.api_pagination import fetch_connection_json

                json_data = fetch_connection_json(conn)
                structure = summarize_json_structure(json_data)
                summary = f"Non-tabular API JSON — {structure}"
                if isinstance(json_data, list):
                    row_n, col_n = len(json_data), 0
                elif isinstance(json_data, dict):
                    row_n, col_n = len(json_data), 0
                else:
                    row_n, col_n = 1, 0
                file_content = build_dataset_metadata(
                    row_n,
                    col_n,
                    "",
                    extra_notes=f"{summary}\nAPI connection: {conn_name}",
                )
                return file_content, None, None
        except Exception as e:
            return f"Error processing API connection: {str(e)}", None, None
