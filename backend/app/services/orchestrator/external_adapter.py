"""External context capability adapter — enforces existing web_search policy."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.web_search import web_search_enabled


def web_search_eligibility(
    *,
    user_tier: str,
    user_question: Optional[str],
    session_ready: bool,
) -> Dict[str, Any]:
    """Availability for the toolbox — model decides whether to call it."""
    if not session_ready:
        return {"available": False, "unavailable_reason": "dataset_not_ready"}
    if not web_search_enabled(user_tier):
        return {"available": False, "unavailable_reason": "plan_not_eligible"}
    if not (user_question or "").strip():
        return {"available": False, "unavailable_reason": "question_empty"}
    return {
        "available": True,
        "unavailable_reason": None,
        "authority": "web_search.run_multi_web_search",
        "provider": "duckduckgo",
    }
