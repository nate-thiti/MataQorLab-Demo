"""Deterministic parsing of user answers to awaiting_user questions."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from app.services.orchestrator.decision_models import UserResolutionProposal

_APPROVE_PATTERNS = (
    r"^(ใช่|ได้|โอเค|ok|okay|yes|y|approve|approved|ทำเลย|ดำเนินการ|อนุมัติ|ตกลง|go)$",
    r"(ทำเลย|ดำเนินการต่อ|อนุมัติ|approve)",
)
_REJECT_PATTERNS = (
    r"^(ไม่|no|n|cancel|reject|rejected|ยกเลิก|ไม่เอา|อย่า|หยุด)$",
    r"(ไม่เอา|อย่าทำ|ยกเลิก|ไม่ดำเนินการ|reject)",
)
_AMBIGUOUS_PATTERNS = (
    r"(ก็แล้วแต่|ไม่แน่ใจ|เอาที่เหมาะ|อะไรก็ได้|แล้วแต่|ไม่รู้|up to you|whatever)",
)
_STANDARD_PROFILE = re.compile(
    r"(standard|มาตรฐาน|เปลี่ยนเป็น\s*standard|ใช้\s*standard)",
    re.IGNORECASE,
)
_CONSERVATIVE_PROFILE = re.compile(
    r"(conservative|ระมัดระวัง)",
    re.IGNORECASE,
)
_FINANCIAL_PROFILE = re.compile(
    r"(financial|การเงิน)",
    re.IGNORECASE,
)
_AGGRESSIVE_PROFILE = re.compile(
    r"(aggressive|deep\s*clean)",
    re.IGNORECASE,
)


def parse_user_resolution(
    message: str,
    *,
    awaiting: Optional[Dict[str, Any]] = None,
) -> UserResolutionProposal:
    text = str(message or "").strip()
    if not text:
        return UserResolutionProposal(decision="ambiguous", note="empty")

    lowered = text.lower().strip()
    for pattern in _AMBIGUOUS_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            return UserResolutionProposal(decision="ambiguous", note="ambiguous_phrase")

    context_updates: Dict[str, Any] = {}
    if _STANDARD_PROFILE.search(text):
        context_updates["cleaning_profile"] = "standard"
    elif _CONSERVATIVE_PROFILE.search(text):
        context_updates["cleaning_profile"] = "conservative"
    elif _FINANCIAL_PROFILE.search(text):
        context_updates["cleaning_profile"] = "financial"
    elif _AGGRESSIVE_PROFILE.search(text) and "ไม่" not in lowered:
        context_updates["cleaning_profile"] = "aggressive"

    # Return-policy style answers (limited Phase 5 support).
    if re.search(r"(สินค้าคืน|คืนสินค้า|return)", text, flags=re.IGNORECASE):
        if re.search(r"(ติดลบ|negative)", text, flags=re.IGNORECASE):
            context_updates.setdefault("return_policy", {
                "value": "negative_transaction",
                "treatment": "include_as_negative",
                "source": "user_confirmed",
            })

    if context_updates:
        return UserResolutionProposal(
            decision="modified",
            context_updates=context_updates,
            note="modified_from_message",
        )

    for pattern in _REJECT_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            return UserResolutionProposal(decision="rejected", note="reject_phrase")

    for pattern in _APPROVE_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            return UserResolutionProposal(decision="approved", note="approve_phrase")

    # Option-id style answers from structured UI.
    if lowered in {"approve", "reject", "modify"}:
        if lowered == "modify":
            return UserResolutionProposal(decision="ambiguous", note="modify_without_details")
        return UserResolutionProposal(
            decision="approved" if lowered == "approve" else "rejected",
            note="option_id",
        )

    del awaiting  # reserved for future reason-code-specific parsers
    return UserResolutionProposal(decision="ambiguous", note="unparsed")
