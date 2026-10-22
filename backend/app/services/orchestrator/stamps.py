"""Deterministic WorklogStamp builders — zero LLM tokens."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, Field


class StampFact(BaseModel):
    label: str
    value: str


class WorklogStamp(BaseModel):
    stamp_id: str
    stamp_type: str
    category: str
    status: str = "completed"
    title: str
    summary: Optional[str] = None
    facts: List[StampFact] = Field(default_factory=list)
    source: Optional[str] = None
    capability_id: Optional[str] = None
    decision_key: Optional[str] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _stamp_id(*parts: Any) -> str:
    raw = "|".join(str(p) for p in parts if p is not None)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _fact(label: str, value: Any) -> Optional[StampFact]:
    if value is None or value == "":
        return None
    return StampFact(label=str(label), value=str(value))


def build_decision_stamp(
    *,
    session_id: str,
    decision_key: str,
    value: Any,
    label: Optional[str] = None,
) -> WorklogStamp:
    display = label or decision_key.replace("_", " ").title()
    facts = [
        f for f in (
            _fact(display, value),
            _fact("Confirmed by", "user"),
        ) if f
    ]
    return WorklogStamp(
        stamp_id=_stamp_id(session_id, "decision", decision_key, value),
        stamp_type="context_confirmed",
        category="decision",
        title="Business context recorded",
        summary=f"{display} → {value}",
        facts=facts,
        source="user_confirmed",
        decision_key=decision_key,
    )


def build_mapping_stamp(
    *,
    session_id: str,
    column: str,
    role: str,
) -> WorklogStamp:
    return WorklogStamp(
        stamp_id=_stamp_id(session_id, "mapping", column, role),
        stamp_type="mapping_confirmed",
        category="mapping",
        title="Mapping confirmed",
        summary=f"{column} → {role}",
        facts=[
            f for f in (
                _fact(column, role),
                _fact("Confirmed by", "user"),
            ) if f
        ],
        source="user_confirmed",
        decision_key=f"mapping:{role}",
        capability_id="map",
    )


def build_tool_stamp(
    *,
    session_id: str,
    step: str,
    tool_summary: Mapping[str, Any],
    version: Any = None,
    attempt: Any = None,
) -> Optional[WorklogStamp]:
    status = str(tool_summary.get("status") or "completed")
    if status not in {"completed", "awaiting_user", "failed"}:
        return None
    stamp_type = {
        "inspect": "source_inspected",
        "prepare": "prepare_completed",
        "clean": "clean_completed",
        "map": "mapping_confirmed",
        "validate": "validation_completed",
        "finalize": "dataset_ready",
    }.get(step, f"{step}_completed")

    facts: List[StampFact] = []
    meta = tool_summary.get("metadata") if isinstance(tool_summary.get("metadata"), Mapping) else {}
    report = {}
    if isinstance(tool_summary.get("cleaning_report"), Mapping):
        report = tool_summary["cleaning_report"]
    elif isinstance(meta.get("cleaning_report"), Mapping):
        report = meta["cleaning_report"]

    for label, key in (
        ("Rows before", "rows_before"),
        ("Rows after", "rows_after"),
        ("Returns retained", "returns_retained"),
        ("Profile", "cleaning_profile"),
        ("Mapped columns", "mapped_columns"),
    ):
        val = report.get(key) if key in report else meta.get(key)
        fact = _fact(label, val)
        if fact:
            facts.append(fact)

    for finding in list(tool_summary.get("findings") or [])[:4]:
        if not isinstance(finding, Mapping):
            continue
        if finding.get("count") is not None:
            fact = _fact(str(finding.get("type") or "finding"), finding.get("count"))
            if fact:
                facts.append(fact)

    titles = {
        "inspect": "Source inspected",
        "prepare": "Data prepared",
        "clean": "Data Cleaning",
        "map": "Schema mapping updated",
        "validate": "Validation completed",
        "finalize": "Dataset ready for analysis",
    }
    return WorklogStamp(
        stamp_id=_stamp_id(session_id, step, version, attempt, status, tool_summary.get("summary")),
        stamp_type=stamp_type,
        category="tool",
        status=status if status != "awaiting_user" else "awaiting_user",
        title=titles.get(step, f"{step} completed"),
        summary=str(tool_summary.get("summary") or "")[:300] or None,
        facts=facts,
        source="workflow_engine",
        capability_id=step,
    )


def build_analytics_stamp(
    *,
    session_id: str,
    request_id: str,
    facts: Mapping[str, Any],
    title: str = "Data query completed",
) -> WorklogStamp:
    stamp_facts = [
        f for k, v in list(facts.items())[:8]
        if (f := _fact(str(k), v))
    ]
    return WorklogStamp(
        stamp_id=_stamp_id(session_id, "analytics", request_id, title),
        stamp_type="analysis_completed",
        category="analytics",
        title=title,
        facts=stamp_facts,
        source="question_analytics",
        capability_id="query_data",
    )


def build_web_search_stamp(
    *,
    session_id: str,
    request_id: str,
    sources_checked: int,
) -> WorklogStamp:
    return WorklogStamp(
        stamp_id=_stamp_id(session_id, "web_search", request_id, sources_checked),
        stamp_type="external_context_searched",
        category="external_context",
        title="External context searched",
        facts=[f for f in (_fact("Sources checked", sources_checked),) if f],
        source="web_search",
        capability_id="web_search",
    )


def stamp_to_dict(stamp: WorklogStamp) -> Dict[str, Any]:
    return stamp.model_dump()


def merge_stamps_idempotent(
    existing: List[Mapping[str, Any]],
    new_stamps: List[WorklogStamp],
    *,
    limit: int = 40,
) -> List[Dict[str, Any]]:
    seen = {str(item.get("stamp_id")) for item in existing if item.get("stamp_id")}
    out = [dict(item) for item in existing]
    for stamp in new_stamps:
        payload = stamp_to_dict(stamp)
        if payload["stamp_id"] in seen:
            continue
        seen.add(payload["stamp_id"])
        out.append(payload)
    return out[-limit:]
