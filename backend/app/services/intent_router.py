"""Deterministic chat intent routing used before expensive LLM calls."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict

from app.services.calculator import calculate_from_question
from app.services.web_search import needs_web_search

_COMPARE_RE = re.compile(
    r"\b(?:compare|versus|vs\.?|benchmark|difference|against)\b"
    r"|เปรียบเทียบ|เทียบ(?:กับ)?|ต่างกัน|เทียบอุตสาหกรรม",
    re.IGNORECASE,
)
_CALCULATE_RE = re.compile(
    r"\b(?:calculate|compute|sum|average|median|percent|ratio|correlation)\b"
    r"|คำนวณ|ยอดรวม|ค่าเฉลี่ย|มัธยฐาน|เปอร์เซ็นต์|อัตราส่วน|สหสัมพันธ์",
    re.IGNORECASE,
)
_ARITHMETIC_RE = re.compile(r"\d[\d,.\s]*(?:[+\-*/%]|×|÷)\s*\d")
_FOLLOW_UP_RE = re.compile(
    r"(?:"
    r"^(?:how about|what about|why|and)\b"
    r"|^(?:แล้ว|ต่อเลย|ต่อ\s|ถ้าอย่างนั้น|อันไหน|ทำไม|เพราะอะไร)"
    r"|ช่วยขยาย|จากคำตอบ|ก่อนหน้า|ข้างต้น|ที่บอกไป|previous answer|above"
    r")",
    re.IGNORECASE,
)
_CURRENT_RE = re.compile(
    r"\b(?:latest|current|today|now|real[- ]?time|news)\b"
    r"|ล่าสุด|ปัจจุบัน|วันนี้|ตอนนี้|ข่าว",
    re.IGNORECASE,
)
_EXTERNAL_COMPARISON_RE = re.compile(
    r"\b(?:market|industry|competitor|external)\b"
    r"|ตลาด|อุตสาหกรรม|คู่แข่ง|ข้อมูลภายนอก",
    re.IGNORECASE,
)
_COMPLEX_RE = re.compile(
    r"\b(?:strategy|scenario|root cause|trade-?off|multi[- ]?step|forecast|correlation)\b"
    r"|กลยุทธ์|จำลองสถานการณ์|หาสาเหตุ|หลายขั้นตอน|พยากรณ์|สหสัมพันธ์",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class IntentDecision:
    primary: str
    needs_web: bool
    needs_dataset: bool
    needs_calculator: bool
    is_comparison: bool
    is_follow_up: bool
    current_data: bool
    complexity: str
    confidence: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_chat_intent(
    question: str,
    *,
    has_dataset: bool = False,
    has_connection: bool = False,
    history_length: int = 0,
) -> IntentDecision:
    text = (question or "").strip()
    comparison = bool(_COMPARE_RE.search(text))
    # Soft hints only (budget/UI). Tool choice is owned by the model planner.
    calculator = bool(
        _ARITHMETIC_RE.search(text) or calculate_from_question(text) is not None
    )
    # Keep keyword calculate verbs as soft complexity hints, not hard tool gates.
    calculator_soft = calculator or bool(_CALCULATE_RE.search(text))
    current = bool(_CURRENT_RE.search(text))
    web = needs_web_search(text) or bool(
        comparison and _EXTERNAL_COMPARISON_RE.search(text)
    )
    dataset = bool(has_dataset or has_connection)

    # Prefer discourse markers; short continuations only when no clear tool intent.
    follow_up = history_length > 1 and bool(_FOLLOW_UP_RE.search(text))
    if (
        history_length > 1
        and not follow_up
        and not web
        and not calculator_soft
        and not dataset
        and (len(text) <= 24 or len(text.split()) <= 3)
    ):
        follow_up = True
    if follow_up and (web or calculator):
        follow_up = False
    if calculator and not dataset:
        follow_up = False

    if dataset and web:
        primary = "dataset_web_comparison" if comparison else "dataset_web"
        reason = "question combines private data with current external evidence"
    elif dataset and calculator_soft:
        primary = "dataset_calculation"
        reason = "question asks for a calculation over attached or connected data"
    elif dataset:
        primary = "dataset_analysis"
        reason = "attached or connected data is available"
    elif web:
        primary = "web_research"
        reason = "question may need current or externally verifiable information"
    elif calculator:
        primary = "calculation"
        reason = "question contains an explicit arithmetic expression"
    elif follow_up:
        primary = "follow_up"
        reason = "question depends on recent conversation context"
    else:
        primary = "general_chat"
        reason = "model will interpret sentence context and select tools if needed"

    complex_request = (
        bool(_COMPLEX_RE.search(text))
        or (comparison and (dataset or web))
        or len(text) > 280
    )
    complexity = "high" if complex_request else "standard"
    confidence = 0.92 if primary not in {"general_chat", "follow_up"} else 0.78
    return IntentDecision(
        primary=primary,
        # Soft routing flags — must not force tool requirements by themselves.
        needs_web=web,
        needs_dataset=dataset,
        needs_calculator=calculator,
        is_comparison=comparison,
        is_follow_up=follow_up,
        current_data=current,
        complexity=complexity,
        confidence=confidence,
        reason=reason,
    )
