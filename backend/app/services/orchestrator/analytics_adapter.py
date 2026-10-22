"""Analytics capability docs for the analysis agent — not executable by WorkflowOrchestrator.

After data setup is ready, chat routes away from the setup controller to the
analysis agent. These helpers document authority only; they never run tools.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def analytics_capabilities_available(session: Mapping[str, Any]) -> bool:
    """True when a ready dataset exists for the analysis agent (not this controller)."""
    return str(session.get("status") or "") == "ready"


def describe_analytics_route(capability_id: str) -> Dict[str, Any]:
    """Document authority mapping without creating duplicate executors."""
    routes = {
        "query_data": {
            "authority": "question_analytics.run_question_aware_analytics",
            "engine": "duckdb",
            "allows_arbitrary_sql_from_ai": False,
        },
        "calculate_metrics": {
            "authority": "analytics_service.calculate_analytics_for_handle",
            "engine": "duckdb_or_domain",
            "allows_arbitrary_sql_from_ai": False,
        },
        "domain_analysis": {
            "authority": "domain_analytics",
            "engine": "deterministic",
            "allows_arbitrary_sql_from_ai": False,
        },
        "generate_findings": {
            "authority": "question_analytics / structured_findings",
            "engine": "duckdb",
            "allows_arbitrary_sql_from_ai": False,
        },
        "evaluate_assurance": {
            "authority": "decision_assurance.build_decision_assurance_packet",
            "engine": "deterministic",
            "allows_arbitrary_sql_from_ai": False,
        },
    }
    return routes.get(capability_id, {"authority": "unknown", "allows_arbitrary_sql_from_ai": False})


def external_search_route() -> Dict[str, Any]:
    return {
        "capability_id": "web_search",
        "authority": "web_search.run_multi_web_search",
        "provider": "duckduckgo",
        "tier_gate": "plus_pro",
        "relevance_gate": "needs_web_search",
    }
