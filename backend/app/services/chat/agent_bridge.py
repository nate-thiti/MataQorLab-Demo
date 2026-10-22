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


class AgentAnalyticsBridge:
    def __init__(self, llm: LlmClient) -> None:
        self.llm = llm

    async def _classify_dataset(self, file_content: str) -> Optional[str]:
        """
        Layer 4: AI Classification - ระบุประเภทของชุดข้อมูลเพื่อช่วยในการวิเคราะห์
        """
        try:
            sample = file_content[:2000]
            prompt = (
                "Classify the following data into exactly one category: "
                "sales_report, inventory_snapshot, warehouse_movement, branch_performance, "
                "financial_accounting, marketing_campaign, human_resources, production_manufacturing, "
                "procurement_purchasing, customer_experience, or general_business_data. "
                "Reply with ONLY the category name.\n\n"
                f"Data Sample:\n{sample}"
            )
            response = await self.llm.safe_chat_completion(
                model=settings.LLM_MODEL_FREE,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=15
            )
            return response.choices[0].message.content.strip().lower()
        except Exception:
            return None

    async def resolve_dataset_type(
        self,
        analytics_results: Optional[Dict[str, Any]],
        file_content: Optional[str],
    ) -> Optional[str]:
        """Prefer role-based inference; fall back to LLM classification."""
        suggested = (analytics_results or {}).get("suggested_dataset_type")
        if suggested and suggested != "general_business_data":
            return suggested
        classified: Optional[str] = None
        if file_content:
            classified = await self._classify_dataset(file_content)
            if classified and classified != "general_business_data":
                return classified
        return suggested or classified

    async def _run_data_agent(
        self,
        data: Union[pd.DataFrame, DatasetHandle],
        user_question: str,
        model: str,
        analytics_results: Optional[Dict[str, Any]],
        user_id: str,
        column_mapping: Optional[Dict[str, str]] = None,
        on_status: Optional[Callable[[str, Optional[Dict[str, Any]]], Awaitable[None]]] = None,
        file_attachment_name: Optional[str] = None,
        connection_id: Optional[str] = None,
        connection_type: Optional[str] = None,
        dataset_type: Optional[str] = None,
        summary: Optional[str] = None,
        sql_query: Optional[str] = None,
        sql_table: Optional[str] = None,
        agent_session: Optional[Any] = None,
        clarification_answer: Optional[str] = None,
        user_tier: str = "free",
        max_agent_steps: Optional[int] = None,
        max_search_queries: int = 3,
        max_search_sources: int = 8,
    ) -> Any:
        async def agent_status(stage: str, detail: Dict[str, Any]) -> None:
            await emit_status(on_status, stage, detail)

        return await run_autonomous_agent_loop(
            data,
            user_question=user_question,
            model=model,
            chat_completion_fn=self.llm.safe_chat_completion,
            user_id=user_id,
            column_mapping=column_mapping,
            analytics_results=analytics_results,
            on_status=agent_status if on_status else None,
            session=agent_session,
            clarification_answer=clarification_answer,
            file_attachment_name=file_attachment_name,
            connection_id=connection_id,
            connection_type=connection_type,
            dataset_type=dataset_type,
            summary=summary,
            sql_query=sql_query,
            sql_table=sql_table,
            user_tier=user_tier,
            max_agent_steps=max_agent_steps,
            max_search_queries=max_search_queries,
            max_search_sources=max_search_sources,
        )

    async def apply_agent_analytics(
        self,
        data: Union[pd.DataFrame, DatasetHandle],
        user_question: str,
        model: str,
        analytics_results: Optional[Dict[str, Any]],
        user_id: str,
        column_mapping: Optional[Dict[str, str]] = None,
        on_status: Optional[Callable[[str, Optional[Dict[str, Any]]], Awaitable[None]]] = None,
        file_attachment_name: Optional[str] = None,
        connection_id: Optional[str] = None,
        connection_type: Optional[str] = None,
        dataset_type: Optional[str] = None,
        summary: Optional[str] = None,
        sql_query: Optional[str] = None,
        sql_table: Optional[str] = None,
        agent_session: Optional[Any] = None,
        clarification_answer: Optional[str] = None,
        user_tier: str = "free",
        cleaning_profile: str = "standard",
        max_agent_steps: Optional[int] = None,
        max_search_queries: int = 3,
        max_search_sources: int = 8,
        cache_provenance: Optional[Dict[str, Any]] = None,
        skip_question_cache: bool = False,
    ) -> tuple[Optional[Dict[str, Any]], Optional[AgentPauseResult], str]:
        use_cache = (
            should_cache_analytics(file_attachment_name, connection_id)
            and not connection_id
            and bool((cache_provenance or {}).get("source_fingerprint"))
            and not agent_session
            and not clarification_answer
            and not skip_question_cache
        )
        qkey = None
        if use_cache:
            qkey = question_cache_key(
                user_id,
                file_attachment_name,
                column_mapping,
                user_question,
                connection_id,
                cleaning_profile,
                cache_provenance,
            )
            cached_out = get_question_result(qkey)
            if cached_out:
                insight = format_specific_insight(cached_out) if cached_out else ""
                if cached_out:
                    analytics_results = merge_into_analytics(analytics_results, cached_out)
                await emit_status(
                    on_status,
                    "analyzing_done",
                    {"hint": user_question[:80], "cached": True},
                )
                return analytics_results, None, insight

        agent_out = await self._run_data_agent(
            data,
            user_question,
            model,
            analytics_results,
            user_id,
            column_mapping=column_mapping,
            on_status=on_status,
            file_attachment_name=file_attachment_name,
            connection_id=connection_id,
            connection_type=connection_type,
            dataset_type=dataset_type,
            summary=summary,
            sql_query=sql_query,
            agent_session=agent_session,
            clarification_answer=clarification_answer,
            sql_table=sql_table,
            user_tier=user_tier,
            max_agent_steps=max_agent_steps,
            max_search_queries=max_search_queries,
            max_search_sources=max_search_sources,
        )
        if isinstance(agent_out, AgentPauseResult):
            return analytics_results, agent_out, ""
        insight = format_specific_insight(agent_out) if agent_out else ""
        if agent_out:
            if use_cache and qkey:
                set_question_result(qkey, agent_out)
            analytics_results = merge_into_analytics(analytics_results, agent_out)
            preview = agent_out.get("formatted", "").replace("\n", " ").strip()[:120]
            web_sources = (analytics_results or {}).get("web_sources") or []
            await emit_status(
                on_status,
                "analyzing_done",
                {
                    "hint": user_question[:80],
                    "preview": preview,
                    **({"web_sources": web_sources} if web_sources else {}),
                },
            )
        return analytics_results, None, insight
