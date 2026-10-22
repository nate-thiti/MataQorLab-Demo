"""LLM client — OpenAI-compatible providers, model resolution, streaming with fallback."""
from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional

import openai
from openai import AsyncOpenAI

from app.core.config import settings
from app.core.openrouter_routing import openrouter_extra_for_model
from app.schemas.chat import ChatRequest
from app.services.intent_router import IntentDecision


def _primary_models() -> tuple[str, ...]:
    return (settings.LLM_MODEL_FREE, settings.LLM_MODEL_PREMIUM)


def resolve_model_mode_for_tier(model_mode: str, tier: str) -> str:
    normalized_tier = (tier or "free").lower()
    if model_mode == "fast":
        return "fast"
    if model_mode == "auto" and normalized_tier in ("plus", "pro"):
        return "auto"
    if model_mode == "deep" and normalized_tier == "pro":
        return "deep"
    return "auto" if normalized_tier in ("plus", "pro") else "fast"


class LlmClient:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            default_headers={
                "HTTP-Referer": settings.APP_REFERER,
                "X-Title": settings.APP_TITLE,
            },
        )

    def _provider_extra_for_model(self, model: str) -> Optional[Dict[str, Any]]:
        return openrouter_extra_for_model(
            settings.LLM_BASE_URL,
            model,
            _primary_models(),
            settings.LLM_PROVIDER_ORDER,
            settings.LLM_PROVIDER_ONLY,
            settings.LLM_PROVIDER_ALLOW_FALLBACKS,
        )

    def resolve_model(
        self,
        chat_request: ChatRequest,
        *,
        intent: Optional[IntentDecision] = None,
    ) -> str:
        user_tier = (chat_request.tier or "free").lower()
        model_mode = resolve_model_mode_for_tier(
            chat_request.model_mode,
            user_tier,
        )
        allowed_models = {
            settings.LLM_MODEL_FREE,
            settings.LLM_MODEL_FREE_FALLBACK,
        }
        if user_tier in ("plus", "pro"):
            allowed_models.update(
                {
                    settings.LLM_MODEL_PREMIUM,
                    settings.LLM_MODEL_PREMIUM_FALLBACK,
                    settings.LLM_MODEL_LIGHT,
                    settings.LLM_MODEL_REASONING,
                }
            )
        if chat_request.model and chat_request.model in allowed_models:
            return chat_request.model
        if user_tier == "pro" and model_mode == "deep":
            return settings.LLM_MODEL_REASONING or settings.LLM_MODEL_PREMIUM
        if user_tier in ("plus", "pro") and model_mode == "fast":
            return settings.LLM_MODEL_LIGHT or settings.LLM_MODEL_PREMIUM
        if user_tier in ("plus", "pro") and intent:
            if (
                user_tier == "pro"
                and intent.complexity == "high"
                and settings.LLM_MODEL_REASONING
            ):
                return settings.LLM_MODEL_REASONING
            if (
                intent.primary in {"general_chat", "follow_up"}
                and settings.LLM_MODEL_LIGHT
            ):
                return settings.LLM_MODEL_LIGHT
        return (
            settings.LLM_MODEL_PREMIUM
            if user_tier in ("plus", "pro")
            else settings.LLM_MODEL_FREE
        )

    def _get_fallback_model(self, model: str) -> Optional[str]:
        if model == settings.LLM_MODEL_FREE:
            return settings.LLM_MODEL_FREE_FALLBACK
        if model == settings.LLM_MODEL_PREMIUM:
            return settings.LLM_MODEL_PREMIUM_FALLBACK
        return None

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        return isinstance(exc, openai.RateLimitError) or (
            isinstance(exc, openai.APIStatusError) and exc.status_code == 429
        )

    async def _chat_completion_once(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int] = None,
        *,
        stream: bool = False,
    ):
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if stream:
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}
        extra = self._provider_extra_for_model(model)
        if extra:
            kwargs["extra_body"] = extra
        return await self.client.chat.completions.create(**kwargs)

    async def safe_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int] = None,
    ):
        response, _calls = await self.safe_chat_completion_with_usage(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response

    async def safe_chat_completion_with_usage(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int] = None,
        *,
        kind: str = "decision",
    ) -> tuple[Any, List[Dict[str, Any]]]:
        """Like safe_chat_completion but returns per-attempt usage records."""
        from app.services.orchestrator.usage import extract_usage_from_response

        calls: List[Dict[str, Any]] = []
        try:
            response = await self._chat_completion_once(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            usage = extract_usage_from_response(response)
            calls.append({
                "kind": kind,
                "model": getattr(response, "model", None) or model,
                "fallback": False,
                "repair_attempt": kind == "repair",
                **usage,
            })
            return response, calls
        except (openai.RateLimitError, openai.APIStatusError) as exc:
            if not self._is_rate_limit_error(exc):
                raise exc
            fallback_model = self._get_fallback_model(model)
            if not fallback_model:
                raise exc
            print(
                f"[Fallback] Primary model {model} rate limited. "
                f"Switching to fallback: {fallback_model}"
            )
            # Primary attempt consumed no countable usage if it failed before a body.
            calls.append({
                "kind": kind,
                "model": model,
                "fallback": False,
                "repair_attempt": kind == "repair",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "error": "rate_limit",
            })
            response = await self._chat_completion_once(
                model=fallback_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            usage = extract_usage_from_response(response)
            calls.append({
                "kind": kind,
                "model": getattr(response, "model", None) or fallback_model,
                "fallback": True,
                "repair_attempt": kind == "repair",
                **usage,
            })
            return response, calls

    async def safe_chat_completion_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[Any]:
        models_to_try = [model]
        fallback = self._get_fallback_model(model)
        if fallback:
            models_to_try.append(fallback)

        last_error: Optional[Exception] = None
        for idx, current_model in enumerate(models_to_try):
            if idx == 1:
                print(
                    f"[Fallback] Primary model {model} rate limited. "
                    f"Switching to fallback: {current_model}"
                )
            try:
                stream = await self._chat_completion_once(
                    model=current_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )
                async for chunk in stream:
                    yield chunk
                return
            except (openai.RateLimitError, openai.APIStatusError) as exc:
                last_error = exc
                if not self._is_rate_limit_error(exc) or idx == len(models_to_try) - 1:
                    raise exc
        if last_error:
            raise last_error
