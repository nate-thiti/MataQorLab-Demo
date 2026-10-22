"""
Legacy analytics facade — delegates to unified analytics pipeline.
"""
from typing import Any, Callable, Dict, Optional

import pandas as pd

from app.services.analytics_service import (
    calculate_analytics_from_dataframe,
    legacy_summary_from_analytics,
)


def run_modern_analytics(
    df: pd.DataFrame,
    column_mapping: Optional[Dict[str, str]] = None,
    pandas_calculator: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Unified analytics for legacy /api/normalize."""
    result = calculate_analytics_from_dataframe(
        df,
        column_mapping,
        pandas_calculator=pandas_calculator,
    )
    return legacy_summary_from_analytics(result)


def run_basic_analytics(data: list) -> Dict[str, Any]:
    """Backward-compatible entry; prefers modern pipeline when data is tabular."""
    if not data:
        return {"summary": {"total_sales": 0, "total_items": 0, "avg_transaction": 0}}
    df = pd.DataFrame(data)
    from app.services.chat import chat_service

    return run_modern_analytics(df, {}, pandas_calculator=chat_service.analytics.calculate)
