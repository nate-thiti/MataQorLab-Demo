"""Ask → Prove → Pin decision-packet helpers (pure + report-facing)."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

ALLOWED_LIFECYCLES = {"draft", "proved", "stale"}
ALLOWED_INSIGHT_ACTION_STATUSES = {"open", "done", "dismissed"}
MAX_PINS = 40
MAX_INSIGHT_ACTIONS = 40


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any, *, maximum: int = 2000, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return text[:maximum]


def empty_decision_packet() -> dict[str, Any]:
    return {
        "lifecycle": "draft",
        "proven_at": None,
        "proven_fingerprint": None,
        "pins": [],
        "insight_actions": {},
        "last_prove": None,
    }


def normalize_decision_packet(raw: Any) -> dict[str, Any]:
    base = empty_decision_packet()
    if not isinstance(raw, dict):
        return base
    lifecycle = str(raw.get("lifecycle") or "draft").strip().lower()
    base["lifecycle"] = lifecycle if lifecycle in ALLOWED_LIFECYCLES else "draft"
    base["proven_at"] = raw.get("proven_at") or None
    base["proven_fingerprint"] = _text(raw.get("proven_fingerprint"), maximum=200) or None
    pins = raw.get("pins") if isinstance(raw.get("pins"), list) else []
    base["pins"] = [normalize_pin(item) for item in pins[:MAX_PINS] if isinstance(item, dict)]
    actions = raw.get("insight_actions") if isinstance(raw.get("insight_actions"), dict) else {}
    normalized_actions: dict[str, Any] = {}
    for key, value in list(actions.items())[:MAX_INSIGHT_ACTIONS]:
        if not isinstance(value, dict):
            continue
        status = str(value.get("status") or "open").strip().lower()
        if status not in ALLOWED_INSIGHT_ACTION_STATUSES:
            status = "open"
        normalized_actions[str(key)[:120]] = {
            "status": status,
            "note": _text(value.get("note"), maximum=1000),
            "owner": _text(value.get("owner"), maximum=160),
            "due": _text(value.get("due"), maximum=40) or None,
            "updated_at": value.get("updated_at") or _utc_now(),
        }
    base["insight_actions"] = normalized_actions
    last_prove = raw.get("last_prove")
    base["last_prove"] = deepcopy(last_prove) if isinstance(last_prove, dict) else None
    return base


def normalize_pin(raw: dict[str, Any]) -> dict[str, Any]:
    verification = raw.get("verification") if isinstance(raw.get("verification"), dict) else {}
    return {
        "id": _text(raw.get("id"), maximum=80, fallback=str(uuid4())),
        "kind": _text(raw.get("kind"), maximum=40, fallback="finding"),
        "title": _text(raw.get("title"), maximum=160, fallback="Pinned finding"),
        "summary": _text(raw.get("summary"), maximum=4000),
        "widget_id": _text(raw.get("widget_id"), maximum=120) or None,
        "source_message_id": _text(raw.get("source_message_id"), maximum=80) or None,
        "conversation_id": _text(raw.get("conversation_id"), maximum=80) or None,
        "formula": _text(raw.get("formula"), maximum=500) or None,
        "verification_status": _text(
            raw.get("verification_status") or verification.get("status"),
            maximum=40,
        ) or None,
        "evidence": deepcopy(raw.get("evidence")) if isinstance(raw.get("evidence"), (dict, list)) else {},
        "claims": [
            _text(item, maximum=500)
            for item in (raw.get("claims") or [])
            if str(item or "").strip()
        ][:12],
        "pinned_at": raw.get("pinned_at") or _utc_now(),
    }


def source_fingerprint(source: dict[str, Any] | None) -> str | None:
    if not isinstance(source, dict):
        return None
    recipe = source.get("cleaning_recipe") if isinstance(source.get("cleaning_recipe"), dict) else {}
    for key in ("source_fingerprint", "contract_hash", "recipe_hash", "dataset_version_id"):
        value = source.get(key) or recipe.get(key)
        if value:
            return str(value)
    file_name = source.get("file_name") or source.get("output_dataset_key")
    return str(file_name) if file_name else None


def evaluate_staleness(
    packet: dict[str, Any],
    *,
    live_fingerprint: str | None,
) -> dict[str, Any]:
    state = normalize_decision_packet(packet)
    proven = state.get("proven_fingerprint")
    is_stale = bool(
        proven
        and live_fingerprint
        and proven != live_fingerprint
    )
    if is_stale and state["lifecycle"] in {"proved", "draft"}:
        state["lifecycle"] = "stale"
    elif is_stale and state["lifecycle"] != "stale":
        state["lifecycle"] = "stale"
    return {
        **state,
        "is_stale": is_stale,
        "live_fingerprint": live_fingerprint,
    }


def kpi_snapshot(computed: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in (computed or {}).get("kpis") or []:
        if not isinstance(item, dict):
            continue
        rows.append({
            "kind": item.get("kind"),
            "label": item.get("label"),
            "field": item.get("field"),
            "value": item.get("value"),
        })
    return rows[:20]


def prove_diff(previous: list[dict[str, Any]] | None, current: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    previous_map = {
        f"{item.get('kind')}|{item.get('label')}|{item.get('field')}": item
        for item in (previous or [])
        if isinstance(item, dict)
    }
    diffs: list[dict[str, Any]] = []
    for item in current or []:
        if not isinstance(item, dict):
            continue
        key = f"{item.get('kind')}|{item.get('label')}|{item.get('field')}"
        before = previous_map.get(key)
        before_value = before.get("value") if before else None
        after_value = item.get("value")
        changed = before is None or before_value != after_value
        if not changed:
            continue
        entry: dict[str, Any] = {
            "label": item.get("label"),
            "field": item.get("field"),
            "kind": item.get("kind"),
            "before": before_value,
            "after": after_value,
        }
        try:
            if before_value is not None and after_value is not None:
                before_num = float(before_value)
                after_num = float(after_value)
                if before_num != 0:
                    entry["change_pct"] = round((after_num - before_num) / abs(before_num) * 100, 2)
        except (TypeError, ValueError):
            pass
        diffs.append(entry)
    return diffs[:20]


def apply_prove(
    packet: dict[str, Any],
    *,
    fingerprint: str | None,
    computed: dict[str, Any] | None,
) -> dict[str, Any]:
    state = normalize_decision_packet(packet)
    previous_kpis = ((state.get("last_prove") or {}).get("kpi_snapshot") or [])
    current_kpis = kpi_snapshot(computed)
    diff = prove_diff(previous_kpis, current_kpis)
    state["lifecycle"] = "proved" if fingerprint else state["lifecycle"]
    state["proven_at"] = _utc_now()
    state["proven_fingerprint"] = fingerprint
    state["is_stale"] = False
    state["live_fingerprint"] = fingerprint
    state["last_prove"] = {
        "at": state["proven_at"],
        "fingerprint": fingerprint,
        "kpi_snapshot": current_kpis,
        "diff": diff,
        "insight_count": len((computed or {}).get("decision_insights") or []),
    }
    return state


def can_mark_final(
    packet: dict[str, Any],
    *,
    report_status: str | None = None,
    has_grounded_story: bool = False,
    decision_insight_count: int = 0,
) -> tuple[bool, str]:
    state = normalize_decision_packet(packet)
    if state.get("is_stale") or state.get("lifecycle") == "stale":
        return False, "Re-prove the decision packet before marking it final."
    if state.get("lifecycle") != "proved" and not state.get("proven_fingerprint"):
        # Allow final when there is durable pin evidence or grounded story without explicit re-prove.
        has_pin_evidence = any(
            pin.get("verification_status") in {"grounded", "verified"}
            or pin.get("evidence")
            or pin.get("claims")
            for pin in state.get("pins") or []
        )
        if not (has_pin_evidence or has_grounded_story or decision_insight_count > 0):
            return False, "Prove or pin at least one evidence-backed finding before marking final."
    if report_status == "final":
        return True, ""
    return True, ""


def upsert_pin(packet: dict[str, Any], pin: dict[str, Any]) -> dict[str, Any]:
    state = normalize_decision_packet(packet)
    next_pin = normalize_pin(pin)
    pins = [
        item for item in state["pins"]
        if item.get("id") != next_pin["id"]
        and not (
            next_pin.get("source_message_id")
            and item.get("source_message_id") == next_pin.get("source_message_id")
            and item.get("kind") == next_pin.get("kind")
        )
    ]
    pins.insert(0, next_pin)
    state["pins"] = pins[:MAX_PINS]
    if state["lifecycle"] == "draft" and (
        next_pin.get("verification_status") in {"grounded", "verified"}
        or next_pin.get("evidence")
        or next_pin.get("claims")
    ):
        # Pinning grounded evidence advances the packet toward proved without a full re-prove.
        state["lifecycle"] = "proved"
        state["proven_at"] = state.get("proven_at") or next_pin.get("pinned_at")
    return state


def set_insight_action(
    packet: dict[str, Any],
    *,
    action_key: str,
    status: str = "open",
    note: str = "",
    owner: str = "",
    due: str | None = None,
) -> dict[str, Any]:
    state = normalize_decision_packet(packet)
    key = _text(action_key, maximum=120)
    if not key:
        return state
    action_status = status if status in ALLOWED_INSIGHT_ACTION_STATUSES else "open"
    state["insight_actions"][key] = {
        "status": action_status,
        "note": _text(note, maximum=1000),
        "owner": _text(owner, maximum=160),
        "due": _text(due, maximum=40) or None,
        "updated_at": _utc_now(),
    }
    return state


def insight_action_key(insight: dict[str, Any], index: int) -> str:
    kind = _text(insight.get("kind"), maximum=40, fallback="insight")
    widget = _text((insight.get("evidence") or {}).get("widget_id"), maximum=80)
    return f"{kind}:{widget or index}"


def enrich_decision_insights(
    insights: list[dict[str, Any]] | None,
    packet: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    state = normalize_decision_packet(packet)
    enriched: list[dict[str, Any]] = []
    for index, insight in enumerate(insights or []):
        if not isinstance(insight, dict):
            continue
        item = deepcopy(insight)
        key = insight_action_key(item, index)
        item["action_key"] = key
        item["action"] = state["insight_actions"].get(key) or {
            "status": "open",
            "note": "",
            "owner": "",
            "due": None,
        }
        enriched.append(item)
    return enriched


def read_packet_from_report(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return empty_decision_packet()
    if isinstance(report.get("decision_packet"), dict) and report.get("decision_packet"):
        return normalize_decision_packet(report.get("decision_packet"))
    spec = report.get("dashboard_spec") if isinstance(report.get("dashboard_spec"), dict) else {}
    nested = spec.get("decision_packet")
    if isinstance(nested, dict):
        return normalize_decision_packet(nested)
    return empty_decision_packet()


def packet_persist_payload(report: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    """Build update fields. Prefer dedicated column; always mirror into dashboard_spec for portability."""
    state = normalize_decision_packet(packet)
    # Drop ephemeral flags before persist.
    state.pop("is_stale", None)
    state.pop("live_fingerprint", None)
    spec = dict(report.get("dashboard_spec") or {})
    spec["decision_packet"] = state
    return {
        "decision_packet": state,
        "dashboard_spec": spec,
        "updated_at": _utc_now(),
    }


def decision_brief(report: dict[str, Any], dashboard: dict[str, Any] | None = None) -> dict[str, Any]:
    packet = evaluate_staleness(
        read_packet_from_report(report),
        live_fingerprint=source_fingerprint((dashboard or {}).get("source") or report.get("source_config")),
    )
    story = (dashboard or {}).get("story") or {}
    insights = enrich_decision_insights(
        (dashboard or {}).get("decision_insights") or [],
        packet,
    )
    return {
        "title": report.get("title"),
        "executive_summary": report.get("executive_summary"),
        "lifecycle": packet.get("lifecycle"),
        "is_stale": packet.get("is_stale"),
        "proven_at": packet.get("proven_at"),
        "pin_count": len(packet.get("pins") or []),
        "pins": packet.get("pins") or [],
        "headline": story.get("headline") or story.get("headline_th"),
        "summary": story.get("summary") or story.get("summary_th"),
        "verified_evidence_count": len(story.get("evidence_ids") or story.get("evidence") or []),
        "decision_insights": insights[:5],
        "open_actions": sum(
            1
            for item in insights
            if (item.get("action") or {}).get("status") == "open"
        ),
    }
