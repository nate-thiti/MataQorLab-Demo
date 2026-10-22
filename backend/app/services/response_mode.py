"""Server-owned execution budgets for the user-facing Auto/Fast/Deep modes."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from app.services.intent_router import IntentDecision


@dataclass(frozen=True)
class ResponseModePolicy:
    requested: str
    effective: str
    max_agent_steps: int
    max_search_queries: int
    max_search_sources: int
    max_output_tokens: int
    history_keep_recent: int
    temperature: float
    compute_depth: str
    max_findings: int
    advanced_statistics: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def output_tokens(self, requested: Optional[int]) -> int:
        return min(requested, self.max_output_tokens) if requested else self.max_output_tokens

    def response_temperature(self, requested: Optional[float]) -> float:
        return min(requested, self.temperature) if requested is not None else self.temperature


_FAST = {
    "max_agent_steps": 2,
    "max_search_queries": 1,
    "max_search_sources": 4,
    "max_output_tokens": 900,
    "history_keep_recent": 8,
    "temperature": 0.35,
    "compute_depth": "base",
    "max_findings": 10,
    "advanced_statistics": False,
}

_DEEP = {
    "max_agent_steps": 5,
    "max_search_queries": 3,
    "max_search_sources": 8,
    "max_output_tokens": 4096,
    "history_keep_recent": 16,
    "temperature": 0.5,
    "compute_depth": "deep",
    "max_findings": 24,
    "advanced_statistics": True,
}


def resolve_response_mode(
    requested: str,
    intent: IntentDecision,
    *,
    agent_step_cap: int = 5,
) -> ResponseModePolicy:
    """Resolve Auto deterministically; explicit Fast/Deep always remain explicit."""
    normalized = requested if requested in {"auto", "fast", "deep"} else "auto"
    if normalized == "auto":
        effective = (
            "deep"
            if intent.complexity == "high"
            or intent.needs_dataset
            or intent.needs_web
            else "fast"
        )
    else:
        effective = normalized
    budget = dict(_DEEP if effective == "deep" else _FAST)
    budget["max_agent_steps"] = min(budget["max_agent_steps"], max(1, agent_step_cap))
    return ResponseModePolicy(
        requested=normalized,
        effective=effective,
        **budget,
    )
