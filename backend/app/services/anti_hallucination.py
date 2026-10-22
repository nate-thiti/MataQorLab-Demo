"""Deterministic anti-hallucination guards for chat answers."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.services.calculator import calculate_from_question
from app.services.server_clock import format_local_answer, server_now

_URL_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)

_LIVE_EXTERNAL_RE = re.compile(
    r"(?:"
    r"\b(?:exchange\s*rate|forex|spot\s*price|gold\s*price|oil\s*price|"
    r"stock\s*price|weather|forecast|inflation|interest\s*rate|"
    r"current\s+(?:price|rate|news|president|ceo|law)|"
    r"latest\s+(?:news|rate|price)|who\s+is\s+the\s+current)\b"
    r"|อัตราแลก|ค่าเงิน|เรท(?:วันนี้|ล่าสุด)|ราคาทอง|ราคาน้ำมัน|"
    r"อากาศวันนี้|พยากรณ์อากาศ|เงินเฟ้อ|ดอกเบี้ย|"
    r"ข่าวล่าสุด|ราคาปัจจุบัน|นายกรัฐมนตรีคนปัจจุบัน|"
    r"ประธานาธิบดีคนปัจจุบัน|ซีอีโอปัจจุบัน"
    r")",
    re.IGNORECASE,
)

_CURRENCY_PAIR_RE = re.compile(
    r"(?<![A-Z])(?:USD|THB|EUR|GBP|JPY|CNY|RMB|AUD|CAD|CHF|SGD|HKD|KRW|INR)"
    r"(?:\s*(?:/|[-–—]|to|into|เป็น|เทียบ(?:กับ)?)\s*|"
    r"\s+)"
    r"(?:USD|THB|EUR|GBP|JPY|CNY|RMB|AUD|CAD|CHF|SGD|HKD|KRW|INR)(?![A-Z])",
    re.IGNORECASE,
)

_DEFINITION_RE = re.compile(
    r"(?:"
    r"\b(?:what\s+(?:does|is|do)\s+.+\s+mean\b|"
    r"\bdefine\b|\bdefinition\s+of\b|\bhow\s+(?:do|does)\s+we\s+define\b|"
    r"\bkpi\s+definition\b|\bbusiness\s+definition\b)"
    r"|หมายถึงอะไร|นิยาม(?:คือ|ของ)|คำนิยาม|นิยาม\s*KPI|"
    r"เรา(?:นับ|คิด|นิยาม).{0,20}(?:ยังไง|อย่างไร|ว่าอย่างไร)"
    r")",
    re.IGNORECASE,
)

_SYSTEM_STATUS_RE = re.compile(
    r"(?:"
    r"\b(?:did\s+(?:my|the)\s+(?:file|upload|etl|schedule|sync)\b|"
    r"\bis\s+(?:my\s+)?(?:file|upload|connection|etl|schedule)\s+(?:ready|done|complete|running|failed)\b|"
    r"\bhow\s+many\s+(?:files|conversations|chats|connections)\s+do\s+i\s+have\b|"
    r"\bcheck\s+(?:my\s+)?(?:upload|etl|schedule|connection)\s+status\b)"
    r"|ไฟล์(?:อัปโหลด|อัพโหลด).{0,12}(?:ยัง|หรือยัง|สำเร็จ|เสร็จ)|"
    r"ETL.{0,12}(?:รัน|สำเร็จ|ล้มเหลว|สถานะ)|"
    r"ตารางเวลา.{0,12}(?:รัน|สำเร็จ|สถานะ)|"
    r"มีกี่(?:ไฟล์|แชท|การเชื่อมต่อ)|"
    r"สถานะ(?:ไฟล์|การอัปโหลด|ETL|ตารางเวลา|การเชื่อมต่อ)"
    r")",
    re.IGNORECASE,
)

_PURE_MATH_HINT_RE = re.compile(
    r"(?:"
    r"\b(?:calculate|compute|what\s+is)\b|"
    r"คำนวณ|เท่าไหร่|ได้เท่าไร|ผลลัพธ์"
    r")",
    re.IGNORECASE,
)

_RELATIVE_PERIOD_RE = re.compile(
    r"(?:"
    r"\b(?:this\s+month|last\s+month|this\s+week|last\s+week|"
    r"this\s+year|ytd|year[- ]to[- ]date|mtd|month[- ]to[- ]date|"
    r"today|yesterday|last\s+\d+\s+days)\b"
    r"|เดือนนี้|เดือนก่อน|สัปดาห์นี้|สัปดาห์ที่แล้ว|ปีนี้|ปีก่อน|"
    r"วันนี้|เมื่อวาน|ย้อนหลัง\s*\d+\s*วัน|จากต้นปี|จากต้นเดือน"
    r")",
    re.IGNORECASE,
)

_DATASET_SIGNAL_RE = re.compile(
    r"(?:"
    r"\b(?:sales|revenue|profit|dataset|csv|excel|report|analyze|"
    r"inventory|margin|kpi|column|row)\b"
    r"|ยอดขาย|รายได้|กำไร|ชุดข้อมูล|วิเคราะห์|สินค้าคงคลัง|รายงาน|ไฟล์|คอลัมน์|แถว"
    r")",
    re.IGNORECASE,
)


def needs_live_external_facts(question: str) -> bool:
    text = (question or "").strip()
    if not text:
        return False
    if _CURRENCY_PAIR_RE.search(text):
        return True
    return bool(_LIVE_EXTERNAL_RE.search(text))


def is_pure_math_question(question: str) -> bool:
    text = (question or "").strip()
    if not text or needs_live_external_facts(text) or _DATASET_SIGNAL_RE.search(text):
        return False
    result = calculate_from_question(text)
    if not result:
        return False
    # Prefer explicit calculate intent or short arithmetic prompts.
    if _PURE_MATH_HINT_RE.search(text):
        return True
    leftover = re.sub(r"[\d\s,.\-+*/()%×÷]", "", text)
    leftover = re.sub(r"(คำนวณ|เท่าไหร่|ได้เท่าไร|calculate|compute|what|is|of|percent|เปอร์เซ็นต์|ค่าเฉลี่ย|average|mean)", "", leftover, flags=re.I)
    return len(leftover.strip()) <= 8


def is_definition_question(question: str) -> bool:
    return bool(_DEFINITION_RE.search(question or ""))


def is_system_status_question(question: str) -> bool:
    return bool(_SYSTEM_STATUS_RE.search(question or ""))


def needs_relative_period_context(question: str) -> bool:
    return bool(_RELATIVE_PERIOD_RE.search(question or ""))


def build_direct_math_answer(*, question: str, locale: str = "th") -> Optional[Dict[str, Any]]:
    calc = calculate_from_question(question)
    if not calc:
        return None
    result = calc["result"]
    expression = calc["expression"]
    if (locale or "th").startswith("en"):
        answer = f"Calculated result: {expression} = {result}"
    else:
        answer = f"ผลลัพธ์ที่คำนวณแล้ว: {expression} = {result}"
    return {
        "answer": answer,
        "tool_result": calc,
        "tool_execution": {
            "policy": "safe_calculator",
            "satisfied": True,
            "calls": [{
                "tool": "safe_calculator",
                "status": "ok",
                "engine": "safe_calculator",
                "expression": expression,
                "result": result,
            }],
            "numeric_evidence_available": True,
        },
    }


def refuse_external_facts_message(*, locale: str = "th", tier: str = "free") -> str:
    if (locale or "th").startswith("en"):
        if (tier or "").lower() in {"plus", "pro", "enterprise"}:
            return (
                "I need live web evidence for this request, but none was retrieved. "
                "I will not invent rates, prices, or current events. Please retry in a moment."
            )
        return (
            "Live external facts (FX, prices, weather, current events) require a Plus or Pro plan "
            "so MataQorLab can fetch web evidence. I will not invent those values."
        )
    if (tier or "").lower() in {"plus", "pro", "enterprise"}:
        return (
            "คำถามนี้ต้องการหลักฐานสดจากเว็บ แต่ระบบยังดึงไม่ได้ "
            "จะไม่เดาเรท ราคา หรือเหตุการณ์ปัจจุบัน ให้ลองอีกครั้งในอีกสักครู่"
        )
    return (
        "ข้อมูลภายนอกแบบสด (เรทเงิน ราคา อากาศ ข่าวปัจจุบัน) ใช้ได้ในแผน Plus หรือ Pro "
        "เพื่อให้ระบบดึงหลักฐานจากเว็บได้ — จะไม่เดาค่าเหล่านี้แทน"
    )


def definition_askback_message(*, locale: str = "th") -> str:
    if (locale or "th").startswith("en"):
        return (
            "I do not have an approved company definition for this term yet, "
            "so I will not invent one. Please tell me your exact definition, "
            "or save it under Settings → Memory / Organization memory, then ask again."
        )
    return (
        "ยังไม่มีนิยามที่อนุมัติในระบบสำหรับคำนี้ จึงจะไม่เดานิยามธุรกิจให้ "
        "โปรดบอกนิยามที่ต้องการใช้ หรือบันทึกไว้ที่ Settings → ความจำ / องค์กร แล้วถามใหม่"
    )


def system_status_message(*, locale: str = "th") -> str:
    if (locale or "th").startswith("en"):
        return (
            "I cannot see live UI status from this chat alone. "
            "Check Files for uploads, Scheduled ETL for run history, "
            "and Settings for plan/organization status. "
            "If you share a dataset or schedule here, I can analyze that evidence."
        )
    return (
        "จากแชทอย่างเดียวยังดูสถานะ UI แบบสดไม่ได้ "
        "ตรวจที่ ไฟล์ สำหรับอัปโหลด, ตั้งเวลา ETL สำหรับประวัติรัน, "
        "และ Settings สำหรับแผน/องค์กร "
        "ถ้าแนบชุดข้อมูลหรือระบุตารางเวลาในแชทนี้ จะวิเคราะห์จากหลักฐานนั้นได้"
    )


def relative_period_prompt_block(*, locale: str = "th") -> str:
    now = server_now(locale=locale)
    local = format_local_answer(now, locale=locale)
    return (
        "<relative_time_anchor>\n"
        f"Authoritative now: {now.isoformat()}\n"
        f"Human: {local}\n"
        "Interpret relative periods (this month, YTD, today, last 7 days) against this clock "
        "and the dataset date column — never invent a different calendar.\n"
        "</relative_time_anchor>"
    )


def scrub_ungrounded_urls(
    answer: str,
    web_sources: Optional[List[Dict[str, Any]]] = None,
    *,
    thai: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    text = answer or ""
    allowed = {
        (source.get("url") or "").rstrip(".,;:!?/").lower()
        for source in (web_sources or [])
        if source.get("url")
    }
    unknown: List[str] = []

    def _replace(match: re.Match[str]) -> str:
        url = match.group(0)
        key = url.rstrip(".,;:!?/").lower()
        if key in allowed:
            return url
        unknown.append(url)
        return ""

    scrubbed = _URL_RE.sub(_replace, text)
    scrubbed = re.sub(r"[ \t]+\n", "\n", scrubbed)
    scrubbed = re.sub(r"\n{3,}", "\n\n", scrubbed).strip()
    if not unknown:
        return answer, {"applied": False, "removed_urls": []}
    notice = (
        "> ระบบตัดลิงก์ที่ไม่อยู่ในหลักฐานที่ดึงมาแล้วออก"
        if thai
        else "> URLs that were not in fetched evidence were removed."
    )
    return "\n\n".join(part for part in [scrubbed, notice] if part), {
        "applied": True,
        "removed_urls": unknown[:20],
    }


def scrub_ungrounded_external_claims(
    answer: str,
    *,
    needs_external: bool,
    web_sources: Optional[List[Dict[str, Any]]] = None,
    thai: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """If external facts were required but no sources exist, withhold inventing answer."""
    if not needs_external:
        return answer, {"applied": False, "reason": "not_required"}
    if web_sources:
        return answer, {"applied": False, "reason": "has_sources"}
    notice = refuse_external_facts_message(
        locale="en" if not thai else "th",
        tier="plus",  # search attempted or should have; still no invent
    )
    return notice, {"applied": True, "reason": "missing_web_evidence"}


_NUMBER_LINE_RE = re.compile(
    r"(?<![\w])(?:[$€£฿¥]\s*)?-?\d[\d,]*(?:\.\d+)?\s*"
    r"(?:%|percent|บาท|ดอลลาร์|ล้าน|พัน|แสน|ร้อย|\bk\b|\bm\b|\bbn\b|\bmillion\b|\bbillion\b)?",
    re.IGNORECASE,
)
_JSON_FENCE_RE = re.compile(r"```json\s*([\s\S]*?)```", re.IGNORECASE)
_YEAR_CLAIM_RE = re.compile(r"\b(19|20)\d{2}\b")


def follow_up_needs_dataset_reattach(question: str, *, has_dataset: bool, is_follow_up: bool) -> bool:
    """Block dataset follow-ups that lack a source — not live web/FX questions.

    Bare relative words like Thai "วันนี้" must not force re-attach when the user
    is asking for exchange rates or other external facts.
    """
    if has_dataset or not is_follow_up:
        return False
    text = question or ""
    if needs_live_external_facts(text):
        return False
    # Relative day words alone are too weak (FX/news often say "today").
    if _DATASET_SIGNAL_RE.search(text):
        return True
    if re.search(
        r"เดือนก่อน|ก่อนหน้า|ช่วงนั้น|that period|previous(?:\s+period)?|last month",
        text,
        re.I,
    ):
        return True
    if _NUMBER_LINE_RE.search(text) and _RELATIVE_PERIOD_RE.search(text):
        return True
    return False



def follow_up_reattach_message(*, locale: str = "th") -> str:
    if (locale or "th").startswith("en"):
        return (
            "This follow-up looks like it needs the dataset again. "
            "Re-attach the file or connection, then ask once more so I can re-query evidence "
            "instead of guessing from the previous answer."
        )
    return (
        "คำถามต่อเนื่องจากนี้น่าจะต้องใช้ชุดข้อมูลอีกครั้ง "
        "โปรดแนบไฟล์หรือการเชื่อมต่อแล้วถามใหม่ เพื่อให้ระบบคำนวณจากหลักฐานใหม่ "
        "แทนการเดาจากคำตอบก่อนหน้า"
    )


def schema_missing_message(*, locale: str = "th") -> str:
    if (locale or "th").startswith("en"):
        return (
            "I cannot analyze this dataset yet because no verified column profile is available. "
            "Re-open or re-attach the source so the server can profile the schema first."
        )
    return (
        "ยังวิเคราะห์ชุดข้อมูลนี้ไม่ได้ เพราะยังไม่มี column profile ที่ยืนยันจากเซิร์ฟเวอร์ "
        "โปรดเปิดหรือแนบแหล่งข้อมูลใหม่ให้ระบบตรวจ schema ก่อน"
    )


def has_column_profile(analytics_results: Optional[Dict[str, Any]]) -> bool:
    if not analytics_results:
        return False
    profile = analytics_results.get("column_profile")
    return bool(str(profile or "").strip())


def build_entity_allowlist(
    *,
    structured_findings: Optional[List[Dict[str, Any]]] = None,
    web_sources: Optional[List[Dict[str, Any]]] = None,
    chat_memory: Optional[Dict[str, Any]] = None,
) -> set[str]:
    allowed: set[str] = set()
    for finding in structured_findings or []:
        for key in ("metric", "label", "dimension", "group", "name", "unit"):
            value = finding.get(key)
            if value is None:
                continue
            token = str(value).strip()
            if len(token) >= 2:
                allowed.add(token.casefold())
        dims = finding.get("dimensions")
        if isinstance(dims, dict):
            for value in dims.values():
                token = str(value).strip()
                if len(token) >= 2:
                    allowed.add(token.casefold())
    for source in web_sources or []:
        for key in ("title", "url"):
            token = str(source.get(key) or "").strip()
            if len(token) >= 2:
                allowed.add(token.casefold())
    governed_items = ((chat_memory or {}).get("governed") or {}).get("items") or []
    for item in governed_items:
        for key in ("title", "content"):
            token = str(item.get(key) or "").strip()
            if token:
                allowed.add(token.casefold()[:240])
    return allowed


def scrub_ungrounded_numbers(
    answer: str,
    *,
    intent_primary: str | None,
    has_tool_evidence: bool,
    thai: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """Freeze numeric claims in general/follow-up answers without tool evidence."""
    primary = (intent_primary or "").strip()
    if primary not in {"general_chat", "follow_up"}:
        return answer, {"applied": False, "reason": "not_general"}
    if has_tool_evidence:
        return answer, {"applied": False, "reason": "has_evidence"}

    removed = 0
    kept: List[str] = []
    for line in (answer or "").splitlines():
        if "```" in line:
            kept.append(line)
            continue
        if _NUMBER_LINE_RE.search(line):
            removed += 1
            continue
        kept.append(line)
    if not removed:
        return answer, {"applied": False, "removed_lines": 0}
    safe = "\n".join(kept).strip()
    notice = (
        "> ระบบตัดตัวเลขที่ไม่มีหลักฐานจากเครื่องมือออกจากคำตอบทั่วไปแล้ว"
        if thai
        else "> Numbers without tool evidence were removed from this general answer."
    )
    return "\n\n".join(part for part in [safe, notice] if part), {
        "applied": True,
        "removed_lines": removed,
    }


def scrub_ungrounded_year_claims(
    answer: str,
    *,
    thai: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """Remove absolute year claims that conflict with the server clock year."""
    current_year = server_now().year
    removed = 0
    kept: List[str] = []
    for line in (answer or "").splitlines():
        years = [int(match.group(0)) for match in _YEAR_CLAIM_RE.finditer(line)]
        # Flag clearly stale absolute years far from now in assertive clock-like sentences.
        if years and any(abs(year - current_year) >= 2 for year in years):
            if re.search(r"ปัจจุบัน|ตอนนี้|today|current(?:ly)?|as of now", line, re.I):
                removed += 1
                continue
        kept.append(line)
    if not removed:
        return answer, {"applied": False, "removed_lines": 0}
    safe = "\n".join(kept).strip()
    notice = (
        f"> ระบบตัดข้อความที่ระบุปีคลาดจากนาฬิกาเซิร์ฟเวอร์ ({current_year}) ออกแล้ว"
        if thai
        else f"> Statements with years inconsistent with the server clock ({current_year}) were removed."
    )
    return "\n\n".join(part for part in [safe, notice] if part), {
        "applied": True,
        "removed_lines": removed,
        "server_year": current_year,
    }


def validate_chart_actions(
    answer: str,
    *,
    structured_findings: Optional[List[Dict[str, Any]]] = None,
    thai: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """Drop render_chart JSON blocks whose numeric points are not in findings."""
    findings = structured_findings or []
    if not findings:
        # Without findings, strip render_chart to avoid fabricated dashboards.
        def _strip(match: re.Match[str]) -> str:
            raw = match.group(1).strip()
            try:
                import json
                payload = json.loads(raw)
            except Exception:
                return match.group(0)
            if isinstance(payload, dict) and payload.get("action") == "render_chart":
                return ""
            return match.group(0)

        scrubbed = _JSON_FENCE_RE.sub(_strip, answer or "")
        scrubbed = re.sub(r"\n{3,}", "\n\n", scrubbed).strip()
        if scrubbed == (answer or "").strip():
            return answer, {"applied": False, "removed_charts": 0}
        notice = (
            "> ระบบตัดกราฟที่ไม่มีหลักฐาน findings ออกแล้ว"
            if thai
            else "> Chart actions without verified findings were removed."
        )
        return "\n\n".join(part for part in [scrubbed, notice] if part), {
            "applied": True,
            "removed_charts": 1,
            "reason": "no_findings",
        }

    allowed_numbers = set()
    for finding in findings:
        value = finding.get("value")
        if isinstance(value, (int, float)):
            allowed_numbers.add(round(float(value), 6))
        for key in ("value", "result"):
            try:
                allowed_numbers.add(round(float(finding.get(key)), 6))
            except (TypeError, ValueError):
                pass

    removed = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal removed
        raw = match.group(1).strip()
        try:
            import json
            payload = json.loads(raw)
        except Exception:
            return match.group(0)
        if not isinstance(payload, dict) or payload.get("action") != "render_chart":
            return match.group(0)
        data = payload.get("data") or []
        if not isinstance(data, list) or not data:
            removed += 1
            return ""
        chart_numbers = []
        for row in data:
            if not isinstance(row, dict):
                continue
            for key, value in row.items():
                if key in {"name", "label", "category"}:
                    continue
                try:
                    chart_numbers.append(round(float(value), 6))
                except (TypeError, ValueError):
                    continue
        if not chart_numbers:
            removed += 1
            return ""
        # Keep chart if at least half of numeric points appear in findings.
        hits = sum(1 for number in chart_numbers if number in allowed_numbers)
        if hits * 2 >= len(chart_numbers):
            return match.group(0)
        removed += 1
        return ""

    scrubbed = _JSON_FENCE_RE.sub(_replace, answer or "")
    scrubbed = re.sub(r"\n{3,}", "\n\n", scrubbed).strip()
    if not removed:
        return answer, {"applied": False, "removed_charts": 0}
    notice = (
        "> ระบบตัดกราฟที่ตัวเลขไม่สอดคล้องกับ findings ที่ยืนยันแล้วออก"
        if thai
        else "> Chart actions that did not match verified findings were removed."
    )
    return "\n\n".join(part for part in [scrubbed, notice] if part), {
        "applied": True,
        "removed_charts": removed,
    }


def scrub_unknown_entities(
    answer: str,
    *,
    allowlist: Optional[set[str]] = None,
    evidence_scope_active: bool = False,
    thai: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """When evidence exists, drop lines that assert unknown quoted entities."""
    if not evidence_scope_active or not allowlist:
        return answer, {"applied": False, "reason": "no_allowlist"}
    removed = 0
    kept: List[str] = []
    quoted = re.compile(r"[\"“”']([^\"“”']{2,80})[\"“”']")
    for line in (answer or "").splitlines():
        suspects = [item.strip() for item in quoted.findall(line)]
        if suspects and any(item.casefold() not in allowlist for item in suspects):
            # Only scrub if the line also makes a numeric/metric assertion.
            if _NUMBER_LINE_RE.search(line) or re.search(r"ยอด|รายได้|sales|revenue|profit", line, re.I):
                removed += 1
                continue
        kept.append(line)
    if not removed:
        return answer, {"applied": False, "removed_lines": 0}
    safe = "\n".join(kept).strip()
    notice = (
        "> ระบบตัดข้อความที่อ้างเอนทิตีนอกหลักฐานออกแล้ว"
        if thai
        else "> Claims about entities outside the evidence allowlist were removed."
    )
    return "\n\n".join(part for part in [safe, notice] if part), {
        "applied": True,
        "removed_lines": removed,
    }


def memory_freshness_notes(
    memory: Optional[Dict[str, Any]],
    *,
    locale: str = "th",
    max_age_hours: int = 72,
) -> List[str]:
    from datetime import datetime, timezone

    notes: List[str] = []
    if not memory:
        return notes
    now = datetime.now(timezone.utc)
    for scope in ("conversation", "project", "evidence", "user"):
        row = memory.get(scope) or {}
        updated = row.get("updated_at")
        if not updated:
            continue
        try:
            stamp = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
        except ValueError:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age_hours = (now - stamp).total_seconds() / 3600.0
        if age_hours > max_age_hours:
            if (locale or "th").startswith("en"):
                notes.append(
                    f"{scope} memory is {int(age_hours)}h old and may be stale; prefer fresher tool evidence."
                )
            else:
                notes.append(
                    f"ความจำ {scope} อายุ {int(age_hours)} ชม. อาจล้าสมัย — ให้ยึดหลักฐานจากเครื่องมือที่ใหม่กว่า"
                )
    return notes


def self_check_claims(
    answer: str,
    *,
    web_sources: Optional[List[Dict[str, Any]]] = None,
    structured_findings: Optional[List[Dict[str, Any]]] = None,
    has_tool_evidence: bool = False,
    thai: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """Final deterministic pass over risky claim types."""
    text = answer or ""
    gates: Dict[str, Any] = {}
    text, year_gate = scrub_ungrounded_year_claims(text, thai=thai)
    gates["year_gate"] = year_gate
    text, chart_gate = validate_chart_actions(
        text,
        structured_findings=structured_findings,
        thai=thai,
    )
    gates["chart_gate"] = chart_gate
    applied = bool(year_gate.get("applied") or chart_gate.get("applied"))
    if not has_tool_evidence and not (web_sources or structured_findings):
        # Soft notice only once if answer still looks overconfident about live facts.
        if needs_live_external_facts(text) and "http" not in text.lower():
            notice = (
                "> คำตอบนี้ไม่มีหลักฐานเครื่องมือสำหรับข้อเท็จจริงสด — โปรดยืนยันก่อนนำไปใช้"
                if thai
                else "> This answer has no tool evidence for live facts — verify before relying on it."
            )
            text = "\n\n".join(part for part in [text.strip(), notice] if part)
            gates["confidence_notice"] = {"applied": True}
            applied = True
    return text, {"applied": applied, "gates": gates}


def enforce_answer_anti_hallucination(
    answer: str,
    *,
    web_sources: Optional[List[Dict[str, Any]]] = None,
    needs_external: bool = False,
    thai: bool = True,
    intent_primary: str | None = None,
    has_tool_evidence: bool = False,
    structured_findings: Optional[List[Dict[str, Any]]] = None,
    chat_memory: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    text, external_gate = scrub_ungrounded_external_claims(
        answer,
        needs_external=needs_external,
        web_sources=web_sources,
        thai=thai,
    )
    if external_gate.get("applied"):
        return text, {
            "applied": True,
            "external_gate": external_gate,
            "url_gate": {"applied": False, "removed_urls": []},
        }

    text, url_gate = scrub_ungrounded_urls(text, web_sources, thai=thai)
    text, number_gate = scrub_ungrounded_numbers(
        text,
        intent_primary=intent_primary,
        has_tool_evidence=has_tool_evidence or bool(web_sources or structured_findings),
        thai=thai,
    )
    allowlist = build_entity_allowlist(
        structured_findings=structured_findings,
        web_sources=web_sources,
        chat_memory=chat_memory,
    )
    text, entity_gate = scrub_unknown_entities(
        text,
        allowlist=allowlist,
        evidence_scope_active=bool(web_sources or structured_findings),
        thai=thai,
    )
    text, self_check = self_check_claims(
        text,
        web_sources=web_sources,
        structured_findings=structured_findings,
        has_tool_evidence=has_tool_evidence or bool(web_sources or structured_findings),
        thai=thai,
    )
    applied = bool(
        url_gate.get("applied")
        or number_gate.get("applied")
        or entity_gate.get("applied")
        or self_check.get("applied")
    )
    return text, {
        "applied": applied,
        "external_gate": external_gate,
        "url_gate": url_gate,
        "number_gate": number_gate,
        "entity_gate": entity_gate,
        "self_check": self_check,
    }
