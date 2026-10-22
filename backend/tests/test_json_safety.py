import json
import math
from decimal import Decimal

import numpy as np
import pandas as pd

from app.core.json_safety import json_safe_dumps, to_json_safe
from app.services.chat.stream_handler import _sse_event


def test_to_json_safe_replaces_non_finite_numbers_recursively():
    payload = {
        "nan": float("nan"),
        "inf": math.inf,
        "nested": [{"value": np.float64("nan")}, {"value": Decimal("NaN")}],
        "pandas": pd.NA,
        "array": np.array([1.0, np.nan]),
    }

    assert to_json_safe(payload) == {
        "nan": None,
        "inf": None,
        "nested": [{"value": None}, {"value": None}],
        "pandas": None,
        "array": [1.0, None],
    }


def test_json_safe_dumps_emits_strict_json():
    raw = json_safe_dumps({"ส่วนลด": float("nan")}, ensure_ascii=False)

    assert raw == '{"ส่วนลด": null}'
    assert json.loads(raw) == {"ส่วนลด": None}


def test_sse_event_emits_parseable_json_with_nan_payload():
    event = _sse_event({"type": "status", "detail": {"ส่วนลด": float("nan")}})

    assert event.startswith("data: ")
    parsed = json.loads(event.removeprefix("data: ").strip())
    assert parsed == {"type": "status", "detail": {"ส่วนลด": None}}
