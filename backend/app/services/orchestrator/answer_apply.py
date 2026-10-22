"""Deterministic application of collect_input answers to session state."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

from app.services.orchestrator.decision_identity import record_confirmed_decision
from app.core.json_safety import to_json_safe
from app.services.etl_pipeline import normalize_data_contract
from app.services.orchestrator.stamps import (
    WorklogStamp,
    build_decision_stamp,
    build_mapping_stamp,
    merge_stamps_idempotent,
)

logger = logging.getLogger("mataqorlab.orchestrator.answer_apply")

_BOOL_TRUE = {
    "ใช่", "yes", "y", "true", "1", "ok", "ยืนยัน",
    "approve", "approved", "พร้อมแล้ว", "ดำเนินการต่อ",
}
_BOOL_FALSE = {
    "ไม่", "ไม่ใช่", "no", "n", "false", "0",
    "reject", "rejected", "ยังไม่พร้อม", "ยังต้องปรับ",
}


def build_active_decision_payload(
    *,
    decision_key: str,
    question: str,
    options: Optional[List[Mapping[str, Any]]] = None,
    step_type: Optional[str] = None,
    reason_code: Optional[str] = None,
    context: Optional[Mapping[str, Any]] = None,
    expected_input: Optional[str] = None,
    free_text_allowed: bool = True,
    status: str = "pending",
) -> Dict[str, Any]:
    """Canonical persisted active_decision — must be complete before awaiting_user."""
    key = str(decision_key or "").strip()
    text = str(question or "").strip()
    opts = [dict(o) for o in list(options or []) if isinstance(o, Mapping)]
    if expected_input:
        expected = str(expected_input).strip()
    elif opts:
        expected = "option_or_text" if free_text_allowed else "single_choice"
    else:
        expected = "free_text"
    payload = {
        "decision_key": key,
        "status": str(status or "pending"),
        "question": text,
        "options": opts,
        "expected_input": expected,
        "free_text_allowed": bool(free_text_allowed),
        "step_type": step_type,
        "reason_code": reason_code,
        "context": dict(context or {}),
    }
    ok, err = validate_active_decision_completeness(payload)
    if not ok:
        raise ValueError(f"incomplete_active_decision:{err}")
    return payload


def validate_active_decision_completeness(
    payload: Optional[Mapping[str, Any]],
) -> Tuple[bool, Optional[str]]:
    if not payload or not isinstance(payload, Mapping):
        return False, "missing_active_decision"
    key = str(payload.get("decision_key") or "").strip()
    if not key:
        return False, "missing_decision_key"
    question = str(payload.get("question") or "").strip()
    if not question:
        return False, "missing_question"
    opts = list(payload.get("options") or [])
    expected = str(payload.get("expected_input") or "").strip().lower()
    free_text = payload.get("free_text_allowed")
    if free_text is None:
        free_text = expected in {"option_or_text", "free_text"} or not opts
    if expected == "single_choice" and not opts:
        return False, "missing_options_for_single_choice"
    if expected == "option_or_text" and not opts:
        return False, "missing_options_for_option_or_text"
    if not opts and not free_text:
        return False, "no_input_mode"
    return True, None


def normalize_active_decision_options(
    options: Optional[List[Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for opt in list(options or []):
        if isinstance(opt, Mapping):
            oid = str(opt.get("id") or opt.get("value") or "").strip()
            label = str(opt.get("label") or oid).strip()
            if not oid or not label:
                continue
            out.append({
                "id": oid,
                "label": label,
                "value": opt.get("value", oid),
            })
        elif hasattr(opt, "id"):
            oid = str(getattr(opt, "id", "") or "").strip()
            label = str(getattr(opt, "label", "") or oid).strip()
            if oid and label:
                out.append({"id": oid, "label": label, "value": oid})
    return out


def parse_simple_answer(
    text: str,
    *,
    decision_key: str,
    options: Optional[list] = None,
) -> Tuple[Optional[Any], Dict[str, Any]]:
    """Return (value, context_updates) for known decision keys. Deterministic first."""
    raw = str(text or "").strip()
    lowered = raw.lower()
    opts = list(options or [])

    # Match option id/label/value exactly.
    for opt in opts:
        if not isinstance(opt, Mapping):
            continue
        candidates = {
            str(opt.get("id") or "").strip().lower(),
            str(opt.get("label") or "").strip().lower(),
            str(opt.get("value") or "").strip().lower(),
        }
        if lowered in candidates or raw in {
            str(opt.get("id") or ""),
            str(opt.get("label") or ""),
            str(opt.get("value") or ""),
        }:
            value = opt.get("value", opt.get("id"))
            return value, _updates_for_key(decision_key, value, opt)

    if decision_key in {"mapping_confirmed", "business_context_reviewed"}:
        if lowered in _BOOL_TRUE or raw in _BOOL_TRUE:
            return True, {decision_key: True}
        if lowered in _BOOL_FALSE or raw in _BOOL_FALSE:
            return False, {decision_key: False}

    if decision_key == "row_grain":
        if lowered in _BOOL_TRUE or raw in _BOOL_TRUE:
            return "invoice_line", {"row_grain": "invoice_line"}
        if "บิล" in raw and "รายการ" not in raw:
            return "invoice", {"row_grain": "invoice"}
        if raw:
            return raw[:200], {"row_grain": raw[:200]}

    if decision_key == "return_policy":
        if lowered in _BOOL_TRUE or raw in _BOOL_TRUE:
            value = "negative_is_return"
            return value, {
                "return_policy": {
                    "value": value,
                    "treatment": "retain_as_return",
                    "source": "user_confirmed",
                }
            }
        if lowered in _BOOL_FALSE or raw in _BOOL_FALSE:
            value = "exclude_negatives"
            return value, {
                "return_policy": {
                    "value": value,
                    "treatment": "exclude",
                    "source": "user_confirmed",
                }
            }

    if decision_key == "primary_metric":
        if lowered in _BOOL_TRUE or "ขาย" in raw or "sales" in lowered:
            return "sales", {"metric_definition": "sales"}
        if raw:
            return raw[:200], {"metric_definition": raw[:200]}

    if decision_key == "business_purpose":
        if lowered in _BOOL_TRUE or "ขาย" in raw:
            return "sales_analysis", {"business_purpose": "sales_analysis"}
        if raw:
            return raw[:200], {"business_purpose": raw[:200]}

    if decision_key == "data_owner" and raw:
        return raw[:200], {"data_owner": raw[:200]}

    if decision_key == "reporting_period_status":
        if "ครบ" in raw or "complete" in lowered:
            return "complete", {"period_status": "complete"}
        if "ไม่ครบ" in raw or "partial" in lowered:
            return "partial", {"period_status": "partial"}
        return "unknown", {"period_status": "unknown"}

    if decision_key.startswith("mapping:") and raw:
        role = decision_key.split(":", 1)[1]
        # Treat answer as column name.
        return raw, {"column_mapping": {raw: role}}

    return None, {}


def _as_bool_confirm(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if text in {v.lower() for v in _BOOL_TRUE}:
        return True
    if text in {v.lower() for v in _BOOL_FALSE}:
        return False
    if isinstance(value, bool):
        return value
    return False


def _updates_for_key(decision_key: str, value: Any, opt: Mapping[str, Any]) -> Dict[str, Any]:
    if decision_key == "return_policy":
        return {
            "return_policy": {
                "value": str(value),
                "treatment": str(opt.get("treatment") or "retain_as_return"),
                "source": "user_confirmed",
            }
        }
    if decision_key == "primary_metric":
        return {"metric_definition": str(value)}
    if decision_key == "reporting_period_status":
        return {"period_status": str(value)}
    if decision_key.startswith("mapping:"):
        role = decision_key.split(":", 1)[1]
        column = str(value)
        return {"column_mapping": {column: role}}
    if decision_key in {"mapping_confirmed", "business_context_reviewed"}:
        # "approve" must become True; bare "modify" is not a successful confirm.
        text = str(value or "").strip().lower()
        if text in {"modify", "modified", "เปลี่ยน"}:
            return {decision_key: False}
        return {decision_key: _as_bool_confirm(value)}
    return {decision_key: value}


def apply_decision_answer(
    client: Any,
    *,
    session_id: str,
    user_id: str,
    session: Mapping[str, Any],
    decision_key: str,
    context_updates: Mapping[str, Any],
    value: Any = None,
) -> Tuple[Dict[str, Any], Optional[WorklogStamp]]:
    """Persist allowlisted contract/mapping updates + stamp. Returns (session, stamp)."""
    from app.services.orchestrator.session_updates import apply_context_updates

    updated = apply_context_updates(
        client,
        session_id=session_id,
        user_id=user_id,
        session=session,
        context_updates=context_updates,
    )
    stamp: Optional[WorklogStamp] = None
    if decision_key.startswith("mapping:") and isinstance(context_updates.get("column_mapping"), Mapping):
        for col, role in context_updates["column_mapping"].items():
            stamp = build_mapping_stamp(session_id=session_id, column=str(col), role=str(role))
            break
    elif value is not None or context_updates:
        display_val = value
        if display_val is None:
            display_val = next(iter(context_updates.values()), "")
        if isinstance(display_val, Mapping):
            display_val = display_val.get("value") or display_val
        stamp = build_decision_stamp(
            session_id=session_id,
            decision_key=decision_key,
            value=display_val,
        )

    display_val = value
    if display_val is None and context_updates:
        display_val = next(iter(context_updates.values()), "")

    progress = dict(updated.get("processing_progress") or {})
    progress = record_confirmed_decision(
        progress,
        session=updated,
        decision_key=decision_key,
        value=display_val,
    )

    if stamp is not None:
        existing = list(progress.get("worklog_stamps") or [])
        progress["worklog_stamps"] = merge_stamps_idempotent(existing, [stamp])
    payload = {
        "processing_progress": to_json_safe(progress),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    client.table("data_setup_sessions").update(payload).eq(
        "id", session_id
    ).eq("user_id", user_id).execute()
    current = dict(updated)
    current["processing_progress"] = progress
    return current, stamp


def persist_stamps_only(
    client: Any,
    *,
    session_id: str,
    user_id: str,
    session: Mapping[str, Any],
    new_stamps: list,
) -> Dict[str, Any]:
    """Append worklog stamps without mutating active_decision."""
    progress = dict(session.get("processing_progress") or {})
    existing = list(progress.get("worklog_stamps") or [])
    if new_stamps:
        progress["worklog_stamps"] = merge_stamps_idempotent(existing, new_stamps)
    payload = {
        "processing_progress": to_json_safe(progress),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    client.table("data_setup_sessions").update(payload).eq(
        "id", session_id
    ).eq("user_id", user_id).execute()
    current = dict(session)
    current["processing_progress"] = progress
    return current


def persist_active_decision_and_stamps(
    client: Any,
    *,
    session_id: str,
    user_id: str,
    session: Mapping[str, Any],
    active_decision: Optional[Mapping[str, Any]],
    new_stamps: list,
) -> Dict[str, Any]:
    progress = dict(session.get("processing_progress") or {})
    if active_decision is None:
        progress.pop("active_decision", None)
    else:
        ok, err = validate_active_decision_completeness(active_decision)
        if not ok:
            logger.warning(
                "incomplete_active_decision_rejected",
                extra={"reason": err, "decision_key": active_decision.get("decision_key")},
            )
            progress.pop("active_decision", None)
        else:
            progress["active_decision"] = dict(active_decision)
    existing = list(progress.get("worklog_stamps") or [])
    if new_stamps:
        progress["worklog_stamps"] = merge_stamps_idempotent(existing, new_stamps)
    payload = {
        "processing_progress": to_json_safe(progress),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    client.table("data_setup_sessions").update(payload).eq(
        "id", session_id
    ).eq("user_id", user_id).execute()
    current = dict(session)
    current["processing_progress"] = progress
    return current
