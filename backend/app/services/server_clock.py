"""Authoritative server wall-clock for chat date/time questions."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Bangkok"

_CLOCK_TOPIC_RE = re.compile(
    r"(?:"
    r"\b(?:what(?:'s|\s+is)\s+(?:the\s+)?(?:current\s+)?(?:date|time|day)\b|"
    r"\bwhat\s+time\s+is\s+it\b|"
    r"\b(?:current|today'?s)\s+(?:date|time)\b|"
    r"\b(?:date|time)\s+(?:today|now)\b)"
    r"|"
    # Explicit Thai clock/date asks — avoid matching bare "วัน" inside "วันนี้" for FX questions.
    r"วันที่(?:เท่าไหร่|กี่|อะไร|เท่าไร)|"
    r"กี่โมง(?:แล้ว)?|"
    r"เวลา(?:เท่าไหร่|กี่|เท่าไร|ตอนนี้|ปัจจุบัน)|"
    r"นาฬิกา|"
    r"(?:ตอนนี้|ปัจจุบัน)\s*(?:วัน(?:ที่)?|เวลา|กี่โมง)|"
    r"(?:วันนี้|ตอนนี้)\s*(?:วันที่|กี่โมง)|"
    r"วันนี้\s*(?:วันที่\s*)?(?:เท่าไหร่|กี่)|"
    r"ตอนนี้\s*(?:วันที่|เวลา)?\s*(?:เท่าไหร่|กี่โมง|กี่)"
    r")",
    re.IGNORECASE,
)

_NON_CLOCK_RE = re.compile(
    r"(?:"
    r"\b(?:sales|revenue|profit|dataset|csv|excel|report|analyze|analysis|"
    r"compare|benchmark|forecast|inventory|margin|kpi|"
    r"usd|thb|eur|gbp|jpy|cny|forex|exchange|rate|price|gold|weather|"
    r"inflation|news)\b"
    r"|ยอดขาย|รายได้|กำไร|ชุดข้อมูล|วิเคราะห์|เปรียบเทียบ|พยากรณ์|สินค้าคงคลัง|"
    r"รายงาน|ไฟล์|คอลัมน์|แถว|ค่าเงิน|อัตราแลก|เรท|ราคาทอง|อากาศ|เงินเฟ้อ|ข่าว"
    r")",
    re.IGNORECASE,
)

_THAI_MONTHS = (
    "",
    "มกราคม",
    "กุมภาพันธ์",
    "มีนาคม",
    "เมษายน",
    "พฤษภาคม",
    "มิถุนายน",
    "กรกฎาคม",
    "สิงหาคม",
    "กันยายน",
    "ตุลาคม",
    "พฤศจิกายน",
    "ธันวาคม",
)


def resolve_timezone(locale: str | None = None, preferred: str | None = None) -> ZoneInfo:
    name = (preferred or "").strip() or DEFAULT_TZ
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def server_now(*, locale: str | None = None, tz_name: str | None = None) -> datetime:
    return datetime.now(resolve_timezone(locale, tz_name))


def is_current_datetime_question(question: str) -> bool:
    text = (question or "").strip()
    if len(text) < 4:
        return False
    return bool(_CLOCK_TOPIC_RE.search(text))


def is_pure_clock_question(question: str) -> bool:
    """True when the user is asking only for the current date/time."""
    text = (question or "").strip()
    if not is_current_datetime_question(text):
        return False
    if _NON_CLOCK_RE.search(text):
        return False
    try:
        from app.services.anti_hallucination import needs_live_external_facts

        if needs_live_external_facts(text):
            return False
    except Exception:
        pass
    # Mixed questions with significant extra intent should still use the LLM.
    stripped = _CLOCK_TOPIC_RE.sub(" ", text)
    stripped = re.sub(r"[^\w\u0E00-\u0E7F\s]", " ", stripped, flags=re.UNICODE)
    leftover = [tok for tok in stripped.split() if len(tok) > 1]
    return len(leftover) <= 4


def format_clock_prompt_line(now: datetime | None = None) -> str:
    current = now or server_now()
    utc = current.astimezone(timezone.utc)
    return (
        f"Server wall clock (authoritative): {current.isoformat()} "
        f"({current.tzname() or DEFAULT_TZ}); UTC={utc.strftime('%Y-%m-%d %H:%M:%S')}Z. "
        "For any question about today's date or the current time, use ONLY this value — "
        "never invent a date from model knowledge."
    )


def format_local_answer(now: datetime, *, locale: str = "th") -> str:
    hour = now.hour
    minute = now.minute
    if (locale or "th").startswith("en"):
        return (
            f"It is currently {now.strftime('%A, %d %B %Y')} "
            f"at {now.strftime('%H:%M')} ({now.tzname() or DEFAULT_TZ})."
        )
    return (
        f"ขณะนี้วันที่ {now.day} {_THAI_MONTHS[now.month]} {now.year} "
        f"เวลา {hour:02d}:{minute:02d} น. ({now.tzname() or DEFAULT_TZ})"
    )


def build_server_clock_tool_result(
    *,
    locale: str = "th",
    tz_name: str | None = None,
) -> dict[str, Any]:
    now = server_now(locale=locale, tz_name=tz_name)
    answer = format_local_answer(now, locale=locale)
    return {
        "engine": "server_clock",
        "success": True,
        "timezone": str(now.tzinfo) if now.tzinfo else DEFAULT_TZ,
        "iso": now.isoformat(),
        "utc": now.astimezone(timezone.utc).isoformat(),
        "answer": answer,
        "day": now.day,
        "month": now.month,
        "year": now.year,
        "hour": now.hour,
        "minute": now.minute,
        "formatted": (
            "Server clock (authoritative wall time):\n"
            f"- local: {now.isoformat()}\n"
            f"- utc: {now.astimezone(timezone.utc).isoformat()}\n"
            f"- answer_text: {answer}\n"
            "Copy answer_text for date/time questions. Do not invent another date."
        ),
    }


def clock_findings(clock_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Expose clock components as verifier-compatible numeric findings."""
    if not isinstance(clock_result, dict):
        return []
    if not (clock_result.get("success") or clock_result.get("iso")):
        return []
    findings: list[dict[str, Any]] = []
    for key in ("year", "month", "day", "hour", "minute"):
        value = clock_result.get(key)
        if isinstance(value, int):
            findings.append({
                "id": f"clock_{key}",
                "metric": f"server_clock_{key}",
                "value": value,
                "unit": key,
                "provenance": {"engine": "server_clock"},
            })
    return findings


def build_direct_clock_answer(
    *,
    locale: str = "th",
    tz_name: str | None = None,
) -> dict[str, Any]:
    tool = build_server_clock_tool_result(locale=locale, tz_name=tz_name)
    return {
        "answer": tool["answer"],
        "tool_result": tool,
        "tool_execution": {
            "policy": "server_clock",
            "satisfied": True,
            "calls": [
                {
                    "tool": "server_clock",
                    "status": "ok",
                    "engine": "server_clock",
                }
            ],
            "numeric_evidence_available": False,
        },
    }
