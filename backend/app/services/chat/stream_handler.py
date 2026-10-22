from __future__ import annotations

import asyncio
import io
import json
import re
import time
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Union

import numpy as np
import openai
import pandas as pd
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.json_safety import json_safe_dumps
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
from app.services.conversation_memory import build_dataset_key
from app.services.answer_verifier import needs_numeric_correction, verify_answer
from app.services.narration_corrector import retry_narration_for_numeric_mismatch
from app.services.tool_execution import enforce_tool_grounding
from app.services.anti_hallucination import enforce_answer_anti_hallucination
from app.services.chat_intelligence import (
    record_chat_quality_event,
    save_chat_memory,
)
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
from app.core.llm_errors import stream_error_payload
from app.services.storage_download import FileAttachmentError


def _sse_event(payload: Dict[str, Any]) -> str:
    return f"data: {json_safe_dumps(payload, ensure_ascii=False)}\n\n"


_SYSTEM_COMMAND_BLOCK = re.compile(r"```json\s*([\s\S]*?)\s*```", re.IGNORECASE)
_SYSTEM_COMMAND_ACTIONS = {
    "render_chart",
    "generate_report",
    "propose_visualization",
}
_MAX_LENGTH_CONTINUATIONS = 2
_CONTINUATION_MAX_TOKENS = 1536


def _merge_usage(
    total: Optional[Dict[str, int]],
    usage: Any,
) -> Optional[Dict[str, int]]:
    """Accumulate provider usage across an initial stream and continuations."""
    if usage is None:
        return total
    current = {
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }
    if total is None:
        return current
    return {
        key: int(total.get(key, 0) or 0) + current[key]
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }


def _continuation_messages(
    messages: List[Dict[str, str]],
    generated_text: str,
) -> List[Dict[str, str]]:
    """Ask the model to finish a response that hit the provider output limit."""
    return [
        *messages,
        {"role": "assistant", "content": generated_text},
        {
            "role": "user",
            "content": (
                "Your previous response was cut off by the output-token limit. "
                "Continue from the exact point where it stopped without repeating "
                "earlier text. Finish the current sentence and the remaining concise "
                "analysis. Include and close every required render_chart or "
                "generate_report JSON code block before ending."
            ),
        },
    ]


def _preserve_system_commands(original: str, rewritten: str) -> str:
    """Keep UI commands when numeric correction rewrites narration prose."""

    def commands(content: str) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        for match in _SYSTEM_COMMAND_BLOCK.finditer(content or ""):
            try:
                payload = json.loads(match.group(1).strip())
            except (json.JSONDecodeError, TypeError):
                continue
            if (
                isinstance(payload, dict)
                and payload.get("action") in _SYSTEM_COMMAND_ACTIONS
            ):
                found.append(
                    (
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        match.group(0),
                    )
                )
        return found

    original_commands = commands(original)
    if not original_commands:
        return rewritten
    rewritten_keys = {key for key, _ in commands(rewritten)}
    missing = [block for key, block in original_commands if key not in rewritten_keys]
    if not missing:
        return rewritten
    return "\n\n".join(part for part in [rewritten.strip(), *missing] if part).strip()


def _remove_system_commands(content: str, actions: set[str]) -> str:
    """Remove UI commands that are replaced by a server-owned Visualization proposal."""

    def replace(match: re.Match[str]) -> str:
        try:
            payload = json.loads(match.group(1).strip())
        except (json.JSONDecodeError, TypeError):
            return match.group(0)
        if isinstance(payload, dict) and payload.get("action") in actions:
            return ""
        return match.group(0)

    return re.sub(r"\n{3,}", "\n\n", _SYSTEM_COMMAND_BLOCK.sub(replace, content or "")).strip()


def _proposal_block(proposal: dict[str, Any]) -> str:
    return "```json\n" + json.dumps(proposal, ensure_ascii=False) + "\n```"


def _verify_answer_safely(
    answer: str,
    *,
    web_sources: List[Dict[str, Any]],
    has_dataset_metrics: bool,
    structured_findings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Verification must never prevent memory persistence or stream completion."""
    try:
        kwargs: Dict[str, Any] = {
            "web_sources": web_sources,
            "has_dataset_metrics": has_dataset_metrics,
        }
        if structured_findings:
            kwargs["structured_findings"] = structured_findings
        return verify_answer(answer, **kwargs)
    except Exception as exc:
        print(f"verify_answer failed: {exc}")
        return {
            "status": "needs_review",
            "evidence_count": len(web_sources) + (1 if has_dataset_metrics else 0),
            "cited_source_count": 0,
            "numeric_claim_count": 0,
            "supported_numeric_claim_count": 0,
            "citation_coverage": 0.0,
            "warnings": ["Answer verification was unavailable for this response."],
            "finding_count": len(structured_findings or []),
        }


class ChatStreamHandler:
    def __init__(self, llm: LlmClient, context: "ChatContextBuilder") -> None:
        self.llm = llm
        self.context = context

    async def stream_chat_completion(self, chat_request: ChatRequest) -> AsyncIterator[str]:
        from app.schemas.chat import sanitize_message_content

        started_at = time.perf_counter()
        status_queue: asyncio.Queue = asyncio.Queue()
        prepare_result: List[Any] = []

        async def on_status(stage: str, detail: Optional[Dict[str, Any]] = None) -> None:
            await status_queue.put({"type": "status", "stage": stage, "detail": detail or {}})

        async def run_prepare() -> None:
            try:
                prepare_result.append(
                    await self.context.prepare(chat_request, on_status=on_status)
                )
            except FileAttachmentError as e:
                prepare_result.append({"prepare_error": str(e), "code": "file_error"})
            except Exception as e:
                print(f"prepare_chat_context failed: {e}")
                prepare_result.append({"prepare_error": str(e), "code": "server_error"})
            finally:
                await status_queue.put(None)

        prepare_task = asyncio.create_task(run_prepare())

        while True:
            item = await status_queue.get()
            if item is None:
                break
            yield _sse_event(item)

        await prepare_task

        if isinstance(prepare_result[0], dict) and "prepare_error" in prepare_result[0]:
            err = prepare_result[0]
            yield _sse_event(
                {
                    "type": "error",
                    "code": err.get("code", "server_error"),
                    "detail": err["prepare_error"],
                }
            )
            return

        model, messages, pause, preparation_metadata = prepare_result[0]
        response_mode = preparation_metadata.get("response_mode") or {}

        if pause:
            pause_event = {
                "type": "agent_pause",
                "session_id": pause.session_id,
                "question": pause.question,
                "reason": pause.reason,
            }
            yield _sse_event(pause_event)
            done_payload = {
                "type": "done",
                "agent_paused": True,
                "agent_session_id": pause.session_id,
                "agent_reason": pause.reason,
                "message": {"role": "assistant", "content": pause.question},
                "model_used": model,
                "usage": None,
                "routing": preparation_metadata.get("intent"),
                "response_mode": response_mode,
            }
            yield _sse_event(done_payload)
            return

        blocked_answer = preparation_metadata.get("blocked_answer")
        if blocked_answer:
            verification = {
                "status": "blocked",
                "warnings": ["Required analytical tool execution did not complete."],
                "tool_grounding_gate": {"applied": True, "reason": "required_tool_failed"},
            }
            yield _sse_event({"type": "token", "content": blocked_answer})
            yield _sse_event(
                {
                    "type": "done",
                    "message": {"role": "assistant", "content": blocked_answer},
                    "model_used": model,
                    "usage": None,
                    "verification": verification,
                    "tool_execution": preparation_metadata.get("tool_execution"),
                    "routing": preparation_metadata.get("intent"),
                    "response_mode": response_mode,
                }
            )
            return

        direct_answer = preparation_metadata.get("direct_answer")
        if direct_answer:
            yield _sse_event({"type": "token", "content": direct_answer})
            yield _sse_event(
                {
                    "type": "done",
                    "message": {"role": "assistant", "content": direct_answer},
                    "model_used": model,
                    "usage": None,
                    "verification": {
                        "status": "grounded",
                        "warnings": [],
                        "tool_grounding_gate": {
                            "applied": True,
                            "reason": "server_clock",
                        },
                    },
                    "tool_execution": preparation_metadata.get("tool_execution"),
                    "routing": preparation_metadata.get("intent"),
                    "response_mode": response_mode,
                }
            )
            return

        if not messages:
            yield _sse_event(
                {
                    "type": "error",
                    "code": "server_error",
                    "detail": "No messages to generate",
                }
            )
            return

        yield _sse_event(
            {
                "type": "status",
                "stage": "generating",
                "detail": {"model": model, "action": "llm_stream"},
            }
        )

        response_outline = preparation_metadata.get("response_outline") or ""
        full_content: List[str] = []
        generated_content: List[str] = []
        if response_outline:
            outline_chunk = response_outline.rstrip() + "\n\n"
            full_content.append(outline_chunk)
            yield _sse_event({"type": "token", "content": outline_chunk})
        model_used = model
        usage_info = None
        finish_reason: Optional[str] = None
        continuation_count = 0
        generation_messages = messages
        requested_max_tokens = min(
            chat_request.max_tokens
            or response_mode.get("max_output_tokens", 2048),
            response_mode.get("max_output_tokens", 2048),
        )
        try:
            while True:
                finish_reason = None
                async for chunk in self.llm.safe_chat_completion_stream(
                    model=model,
                    messages=generation_messages,
                    temperature=min(
                        chat_request.temperature
                        if chat_request.temperature is not None
                        else response_mode.get("temperature", 0.5),
                        response_mode.get("temperature", 0.5),
                    ),
                    max_tokens=(
                        requested_max_tokens
                        if continuation_count == 0
                        else min(requested_max_tokens, _CONTINUATION_MAX_TOKENS)
                    ),
                ):
                    if getattr(chunk, "model", None):
                        model_used = chunk.model or model_used
                    if getattr(chunk, "usage", None):
                        usage_info = _merge_usage(usage_info, chunk.usage)
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    if getattr(choice, "finish_reason", None):
                        finish_reason = choice.finish_reason
                    delta = choice.delta.content
                    if delta:
                        generated_content.append(delta)
                        full_content.append(delta)

                if (
                    finish_reason != "length"
                    or continuation_count >= _MAX_LENGTH_CONTINUATIONS
                ):
                    break

                continuation_count += 1
                yield _sse_event(
                    {
                        "type": "status",
                        "stage": "continuing",
                        "detail": {
                            "action": "finish_truncated_response",
                            "attempt": continuation_count,
                        },
                    }
                )
                generation_messages = _continuation_messages(
                    messages,
                    "".join(generated_content),
                )
        except openai.RateLimitError as e:
            yield _sse_event(stream_error_payload(e))
            return
        except openai.APIStatusError as e:
            yield _sse_event(stream_error_payload(e))
            return
        except Exception as e:
            yield _sse_event(stream_error_payload(e))
            return

        assistant_text = sanitize_message_content("".join(full_content)) if full_content else ""
        original_assistant_text = assistant_text
        generated_text = sanitize_message_content("".join(generated_content))
        visualization_proposal = preparation_metadata.get("visualization_proposal")
        if isinstance(visualization_proposal, dict):
            generated_text = _remove_system_commands(
                generated_text,
                {"render_chart", "generate_report", "propose_visualization"},
            )
            assistant_text = sanitize_message_content(
                f"{response_outline.rstrip()}\n\n{generated_text}".strip()
                if response_outline
                else generated_text
            )
        user_question = next(
            (m.content for m in reversed(chat_request.messages) if m.role.value == "user"),
            "",
        )
        dataset_key = build_dataset_key(
            chat_request.file_attachment_name,
            chat_request.connection_id,
            chat_request.connection_type,
        )
        structured_findings = preparation_metadata.get("structured_findings") or []
        verification = _verify_answer_safely(
            generated_text,
            web_sources=preparation_metadata.get("web_sources") or [],
            has_dataset_metrics=bool(
                preparation_metadata.get("has_dataset_metrics")
            ),
            structured_findings=structured_findings,
        )
        numeric_correction: Dict[str, Any] = {"attempted": False, "applied": False}
        if needs_numeric_correction(verification) and structured_findings:
            yield _sse_event(
                {
                    "type": "status",
                    "stage": "correcting",
                    "detail": {
                        "action": "fix_numeric_mismatch",
                        "unmatched_claims": verification.get(
                            "unmatched_dataset_numeric_claims"
                        )
                        or [],
                    },
                }
            )
            corrected_text, numeric_correction = await retry_narration_for_numeric_mismatch(
                generated_text,
                structured_findings=structured_findings,
                verification=verification,
                model=model_used,
                chat_completion_fn=self.llm.safe_chat_completion,
                response_mode=response_mode,
            )
            if numeric_correction.get("applied"):
                generated_text = sanitize_message_content(corrected_text)
                assistant_text = sanitize_message_content(
                    f"{response_outline.rstrip()}\n\n{generated_text}".strip()
                    if response_outline
                    else generated_text
                )
                if isinstance(visualization_proposal, dict):
                    assistant_text = _remove_system_commands(
                        assistant_text,
                        {"render_chart", "generate_report", "propose_visualization"},
                    )
                else:
                    assistant_text = _preserve_system_commands(
                        original_assistant_text,
                        assistant_text,
                    )
                verification = _verify_answer_safely(
                    generated_text,
                    web_sources=preparation_metadata.get("web_sources") or [],
                    has_dataset_metrics=bool(
                        preparation_metadata.get("has_dataset_metrics")
                    ),
                    structured_findings=structured_findings,
                )
        generated_text, grounding_gate = enforce_tool_grounding(
            generated_text,
            verification,
            thai=bool(re.search(r"[\u0E00-\u0E7F]", user_question)),
        )
        thai_answer = bool(re.search(r"[\u0E00-\u0E7F]", user_question))
        generated_text, anti_hallucination_gate = enforce_answer_anti_hallucination(
            generated_text,
            web_sources=preparation_metadata.get("web_sources") or [],
            needs_external=bool((preparation_metadata.get("intent") or {}).get("needs_web")),
            thai=thai_answer,
            intent_primary=(preparation_metadata.get("intent") or {}).get("primary"),
            has_tool_evidence=bool(
                preparation_metadata.get("has_tool_evidence")
                or preparation_metadata.get("has_dataset_metrics")
            ),
            structured_findings=structured_findings,
            chat_memory=preparation_metadata.get("chat_memory"),
        )
        if grounding_gate.get("applied") or anti_hallucination_gate.get("applied"):
            assistant_text = sanitize_message_content(
                f"{response_outline.rstrip()}\n\n{generated_text}".strip()
                if response_outline
                else generated_text
            )
            if isinstance(visualization_proposal, dict):
                assistant_text = _remove_system_commands(
                    assistant_text,
                    {"render_chart", "generate_report", "propose_visualization"},
                )
            verification = _verify_answer_safely(
                generated_text,
                web_sources=preparation_metadata.get("web_sources") or [],
                has_dataset_metrics=bool(
                    preparation_metadata.get("has_dataset_metrics")
                ),
                structured_findings=structured_findings,
            )
        verification["tool_grounding_gate"] = grounding_gate
        verification["anti_hallucination_gate"] = anti_hallucination_gate
        if isinstance(visualization_proposal, dict):
            assistant_text = "\n\n".join(
                part
                for part in [
                    assistant_text.strip(),
                    _proposal_block(visualization_proposal),
                ]
                if part
            )
        streamed_tail = generated_text.strip()
        if isinstance(visualization_proposal, dict):
            streamed_tail = "\n\n".join(
                part
                for part in [streamed_tail, _proposal_block(visualization_proposal)]
                if part
            )
        if streamed_tail:
            yield _sse_event({"type": "token", "content": streamed_tail})
        save_chat_memory(
            chat_request.user_id,
            chat_request.conversation_id,
            user_question,
            generated_text,
            web_sources=preparation_metadata.get("web_sources") or [],
            dataset_key=dataset_key,
            computed_facts=structured_findings,
        )
        yield _sse_event(
            {
                "type": "status",
                "stage": "verifying",
                "detail": {
                    **verification,
                    "action": "check_evidence_and_numbers",
                    "numeric_correction": numeric_correction,
                },
            }
        )
        elapsed_ms = round((time.perf_counter() - started_at) * 1000)
        quality_payload = {
            "intent": preparation_metadata.get("intent"),
            "model": model_used,
            "usage": usage_info,
            "latency_ms": elapsed_ms,
            "source_count": len(preparation_metadata.get("web_sources") or []),
            "search_queries": preparation_metadata.get("search_queries") or [],
            "verification": verification,
            "numeric_correction": numeric_correction,
            "tool_execution": preparation_metadata.get("tool_execution"),
            "finish_reason": finish_reason,
            "generation_continuations": continuation_count,
            "generation_truncated": finish_reason == "length",
            "visualization_proposal": bool(visualization_proposal),
            "finding_ids": [
                item.get("id")
                for item in preparation_metadata.get("structured_findings") or []
            ],
            "audit_id": (preparation_metadata.get("analysis_audit") or {}).get("audit_id"),
        }
        record_chat_quality_event(
            chat_request.user_id,
            chat_request.conversation_id,
            "response_generated",
            quality_payload,
        )
        log_pipeline_event(
            "chat_complete",
            user_id=chat_request.user_id,
            model=model_used,
            tokens=usage_info,
            file=chat_request.file_attachment_name,
        )
        done_payload = {
            "type": "done",
            "message": {"role": "assistant", "content": assistant_text},
            "model_used": model_used,
            "usage": usage_info,
            "verification": verification,
            "numeric_correction": numeric_correction,
            "tool_execution": preparation_metadata.get("tool_execution"),
            "finish_reason": finish_reason,
            "generation_continuations": continuation_count,
            "generation_truncated": finish_reason == "length",
            "visualization_proposal": bool(visualization_proposal),
            "routing": preparation_metadata.get("intent"),
            "response_mode": response_mode,
            "search_queries": preparation_metadata.get("search_queries") or [],
            "latency_ms": elapsed_ms,
            "finding_summary": {
                "count": len(preparation_metadata.get("structured_findings") or []),
                "ids": [
                    item.get("id")
                    for item in preparation_metadata.get("structured_findings") or []
                ],
                "compute_depth": response_mode.get("compute_depth"),
            },
            "analysis_audit": preparation_metadata.get("analysis_audit"),
        }
        yield _sse_event(done_payload)


    async def get_chat_completion(self, chat_request: ChatRequest) -> ChatResponse:
        started_at = time.perf_counter()
        model, messages, pause, preparation_metadata = await self.context.prepare(
            chat_request
        )
        response_mode = preparation_metadata.get("response_mode") or {}
        if pause:
            return ChatResponse(
                message=Message.from_assistant(pause.question),
                model_used=model,
                usage=None,
                agent_paused=True,
                agent_session_id=pause.session_id,
                response_mode=response_mode,
                tool_execution=preparation_metadata.get("tool_execution"),
            )
        blocked_answer = preparation_metadata.get("blocked_answer")
        if blocked_answer:
            return ChatResponse(
                message=Message.from_assistant(blocked_answer),
                model_used=model,
                usage=None,
                verification={
                    "status": "blocked",
                    "warnings": ["Required analytical tool execution did not complete."],
                    "tool_grounding_gate": {"applied": True, "reason": "required_tool_failed"},
                },
                routing=preparation_metadata.get("intent"),
                response_mode=response_mode,
                tool_execution=preparation_metadata.get("tool_execution"),
            )
        direct_answer = preparation_metadata.get("direct_answer")
        if direct_answer:
            return ChatResponse(
                message=Message.from_assistant(direct_answer),
                model_used=model,
                usage=None,
                verification={
                    "status": "grounded",
                    "warnings": [],
                    "tool_grounding_gate": {"applied": True, "reason": "server_clock"},
                },
                routing=preparation_metadata.get("intent"),
                response_mode=response_mode,
                tool_execution=preparation_metadata.get("tool_execution"),
            )
        if not messages:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to prepare chat context",
            )
        try:
            response = await self.llm.safe_chat_completion(
                model=model,
                messages=messages,
                temperature=min(
                    chat_request.temperature
                    if chat_request.temperature is not None
                    else response_mode.get("temperature", 0.5),
                    response_mode.get("temperature", 0.5),
                ),
                max_tokens=min(
                    chat_request.max_tokens or response_mode.get("max_output_tokens", 2048),
                    response_mode.get("max_output_tokens", 2048),
                ),
            )
            generated_content = response.choices[0].message.content or ""
            response_outline = preparation_metadata.get("response_outline") or ""
            structured_findings = preparation_metadata.get("structured_findings") or []
            verification = _verify_answer_safely(
                generated_content,
                web_sources=preparation_metadata.get("web_sources") or [],
                has_dataset_metrics=bool(
                    preparation_metadata.get("has_dataset_metrics")
                ),
                structured_findings=structured_findings,
            )
            numeric_correction: Dict[str, Any] = {"attempted": False, "applied": False}
            if needs_numeric_correction(verification) and structured_findings:
                corrected_text, numeric_correction = await retry_narration_for_numeric_mismatch(
                    generated_content,
                    structured_findings=structured_findings,
                    verification=verification,
                    model=response.model or model,
                    chat_completion_fn=self.llm.safe_chat_completion,
                    response_mode=response_mode,
                )
                if numeric_correction.get("applied"):
                    generated_content = corrected_text
                    verification = _verify_answer_safely(
                        generated_content,
                        web_sources=preparation_metadata.get("web_sources") or [],
                        has_dataset_metrics=bool(
                            preparation_metadata.get("has_dataset_metrics")
                        ),
                        structured_findings=structured_findings,
                    )
            generated_content, grounding_gate = enforce_tool_grounding(
                generated_content,
                verification,
                thai=bool(
                    re.search(
                        r"[\u0E00-\u0E7F]",
                        next(
                            (
                                message.content
                                for message in reversed(chat_request.messages)
                                if message.role.value == "user"
                            ),
                            "",
                        ),
                    )
                ),
            )
            user_question_for_gate = next(
                (m.content for m in reversed(chat_request.messages) if m.role.value == "user"),
                "",
            )
            generated_content, anti_hallucination_gate = enforce_answer_anti_hallucination(
                generated_content,
                web_sources=preparation_metadata.get("web_sources") or [],
                needs_external=bool((preparation_metadata.get("intent") or {}).get("needs_web")),
                thai=bool(re.search(r"[\u0E00-\u0E7F]", user_question_for_gate)),
                intent_primary=(preparation_metadata.get("intent") or {}).get("primary"),
                has_tool_evidence=bool(
                    preparation_metadata.get("has_tool_evidence")
                    or preparation_metadata.get("has_dataset_metrics")
                ),
                structured_findings=structured_findings,
                chat_memory=preparation_metadata.get("chat_memory"),
            )
            if grounding_gate.get("applied") or anti_hallucination_gate.get("applied"):
                verification = _verify_answer_safely(
                    generated_content,
                    web_sources=preparation_metadata.get("web_sources") or [],
                    has_dataset_metrics=bool(
                        preparation_metadata.get("has_dataset_metrics")
                    ),
                    structured_findings=structured_findings,
                )
            verification["tool_grounding_gate"] = grounding_gate
            verification["anti_hallucination_gate"] = anti_hallucination_gate
            ai_message = Message.from_assistant(
                f"{response_outline.rstrip()}\n\n{generated_content}".strip()
                if response_outline
                else generated_content
            )
            usage_info = None
            if response.usage:
                usage_info = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            user_question = next(
                (m.content for m in reversed(chat_request.messages) if m.role.value == "user"),
                "",
            )
            dataset_key = build_dataset_key(
                chat_request.file_attachment_name,
                chat_request.connection_id,
                chat_request.connection_type,
            )
            save_chat_memory(
                chat_request.user_id,
                chat_request.conversation_id,
                user_question,
                generated_content,
                web_sources=preparation_metadata.get("web_sources") or [],
                dataset_key=dataset_key,
                computed_facts=structured_findings,
            )
            record_chat_quality_event(
                chat_request.user_id,
                chat_request.conversation_id,
                "response_generated",
                {
                    "intent": preparation_metadata.get("intent"),
                    "model": response.model or model,
                    "usage": usage_info,
                    "latency_ms": round(
                        (time.perf_counter() - started_at) * 1000
                    ),
                    "source_count": len(
                        preparation_metadata.get("web_sources") or []
                    ),
                    "verification": verification,
                    "numeric_correction": numeric_correction,
                    "tool_execution": preparation_metadata.get("tool_execution"),
                    "finding_ids": [
                        item.get("id")
                        for item in structured_findings
                    ],
                    "audit_id": (preparation_metadata.get("analysis_audit") or {}).get("audit_id"),
                },
            )
            return ChatResponse(
                message=ai_message,
                model_used=response.model or model,
                usage=usage_info,
                verification=verification,
                routing=preparation_metadata.get("intent"),
                response_mode=response_mode,
                analysis_audit=preparation_metadata.get("analysis_audit"),
                tool_execution=preparation_metadata.get("tool_execution"),
            )
        except openai.RateLimitError as e:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"โมเดลฟรีของ LLM provider หนาแน่นชั่วคราว (Rate Limit): {str(e)}",
            )
        except openai.APIStatusError as e:
            raise HTTPException(
                status_code=e.status_code,
                detail=f"LLM API Error ({e.status_code}): {str(e)}",
            )
        except Exception as e:
            raise e
