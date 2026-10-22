"""OpenRouter provider routing — passed via extra_body on chat completion requests."""
from __future__ import annotations

from typing import Any, Dict, Optional


def _parse_provider_slugs(raw: str) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def build_openrouter_extra_body(
    base_url: str,
    provider_order: str,
    provider_only: str,
    allow_fallbacks: bool,
) -> Optional[Dict[str, Any]]:
    """Build OpenRouter `provider` object for extra_body, or None if not configured."""
    if "openrouter.ai" not in (base_url or ""):
        return None

    order = _parse_provider_slugs(provider_order)
    if not order:
        return None

    only = _parse_provider_slugs(provider_only) or order
    return {
        "provider": {
            "order": order,
            "only": only,
            "allow_fallbacks": allow_fallbacks,
        }
    }


def openrouter_extra_for_model(
    base_url: str,
    model: str,
    primary_models: tuple[str, ...],
    provider_order: str,
    provider_only: str,
    allow_fallbacks: bool,
) -> Optional[Dict[str, Any]]:
    """Apply provider pinning only for primary tier models (not fallbacks)."""
    if model not in primary_models:
        return None
    return build_openrouter_extra_body(
        base_url,
        provider_order,
        provider_only,
        allow_fallbacks,
    )
