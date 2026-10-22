"""Helpers for producing standards-compliant JSON payloads."""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy is part of the app runtime
    np = None

try:
    import pandas as pd
except ImportError:  # pragma: no cover - pandas is part of the app runtime
    pd = None


def to_json_safe(value: Any) -> Any:
    """Recursively convert non-JSON values like NaN/Infinity to null."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if pd is not None:
        try:
            missing = pd.isna(value)
            if isinstance(missing, (bool, np.bool_ if np is not None else bool)) and missing:
                return None
        except (TypeError, ValueError):
            pass
    if np is not None and isinstance(value, np.generic):
        return to_json_safe(value.item())
    if np is not None and isinstance(value, np.ndarray):
        return to_json_safe(value.tolist())
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_json_safe(item) for item in value]

    try:
        if np is not None and bool(np.isscalar(value)) and bool(np.isnan(value)):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass

    return str(value)


def json_safe_dumps(value: Any, **kwargs: Any) -> str:
    return json.dumps(to_json_safe(value), allow_nan=False, **kwargs)
