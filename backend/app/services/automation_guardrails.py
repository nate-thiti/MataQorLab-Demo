"""Deterministic gates evaluated before scheduled report delivery."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}
DEFAULT_CONFIG: dict[str, Any] = {
    "delivery_enabled": False,
    "recipient_opt_in": False,
    "recipient": "",
    "muted": False,
    "minimum_severity": "info",
    "cooldown_minutes": 1440,
    "significant_change_percent": 0.0,
    "significant_kpi_change_percent": 0.0,
    "require_complete_period": True,
    "max_source_age_hours": 48,
    "preview_acknowledged": False,
    "ai_narration_enabled": True,
    "locale": "th",
}


def normalize_automation_config(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    config = dict(DEFAULT_CONFIG)
    for key in (
        "delivery_enabled",
        "recipient_opt_in",
        "muted",
        "require_complete_period",
        "preview_acknowledged",
    ):
        config[key] = bool(raw.get(key, config[key]))
    config["recipient"] = str(raw.get("recipient") or "").strip()[:320]
    severity = str(raw.get("minimum_severity") or "info").lower()
    config["minimum_severity"] = severity if severity in SEVERITY_RANK else "info"
    config["cooldown_minutes"] = max(
        0, min(int(raw.get("cooldown_minutes") or 0), 43_200)
    )
    config["significant_change_percent"] = max(
        0.0, min(float(raw.get("significant_change_percent") or 0), 100.0)
    )
    config["significant_kpi_change_percent"] = max(
        0.0, min(float(raw.get("significant_kpi_change_percent") or 0), 100.0)
    )
    config["ai_narration_enabled"] = bool(raw.get("ai_narration_enabled", True))
    config["locale"] = "en" if str(raw.get("locale") or "th").lower() == "en" else "th"
    config["max_source_age_hours"] = max(
        1, min(int(raw.get("max_source_age_hours") or 48), 8_760)
    )
    runtime = raw.get("runtime") if isinstance(raw.get("runtime"), dict) else {}
    config["runtime"] = {
        key: runtime.get(key)
        for key in ("last_fingerprint", "last_eligible_at", "last_decision", "last_kpi_snapshot")
        if runtime.get(key) is not None
    }
    return config


def fingerprint_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def evaluate_delivery_candidate(
    *,
    config: Any,
    data_contract: Any,
    fingerprint: str,
    previous_fingerprint: str | None,
    current_rows: int,
    previous_rows: int | None,
    source_updated_at: Any,
    quality_alerts: list[dict[str, Any]] | None = None,
    current_kpis: dict[str, Any] | None = None,
    previous_kpis: dict[str, Any] | None = None,
    last_eligible_at: Any = None,
    now: datetime | None = None,
    delivery_channels: list[str] | None = None,
    chat_target_valid: bool = False,
) -> dict[str, Any]:
    policy = normalize_automation_config(config)
    contract = data_contract if isinstance(data_contract, dict) else {}
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []

    channels = {
        str(channel).lower()
        for channel in (
            delivery_channels
            if delivery_channels is not None
            else (["email"] if policy["delivery_enabled"] else [])
        )
        if str(channel).lower() in {"email", "chat"}
    }
    if not channels:
        reasons.append("delivery_disabled")
    if "email" in channels:
        if not policy["recipient_opt_in"] or not policy["recipient"]:
            reasons.append("recipient_not_opted_in")
        elif (
            parseaddr(policy["recipient"])[1] != policy["recipient"]
            or "@" not in policy["recipient"]
            or "." not in policy["recipient"].rsplit("@", 1)[-1]
        ):
            reasons.append("recipient_invalid")
    if "chat" in channels and not chat_target_valid:
        reasons.append("chat_target_invalid")
    if policy["muted"]:
        reasons.append("muted")
    if not policy["preview_acknowledged"]:
        reasons.append("preview_required")
    if policy["require_complete_period"] and contract.get("period_status") != "complete":
        reasons.append("incomplete_period")

    source_time = _parse_datetime(source_updated_at)
    if source_time is None:
        reasons.append("source_freshness_unknown")
        source_age_hours = None
    else:
        source_age_hours = max(0.0, (now - source_time).total_seconds() / 3600)
        if source_age_hours > policy["max_source_age_hours"]:
            reasons.append("stale_source")

    if previous_fingerprint and previous_fingerprint == fingerprint:
        reasons.append("duplicate_fingerprint")

    row_change_percent = None
    if previous_rows is not None:
        denominator = max(abs(previous_rows), 1)
        row_change_percent = abs(current_rows - previous_rows) / denominator * 100
        if (
            fingerprint != previous_fingerprint
            and row_change_percent < policy["significant_change_percent"]
        ):
            reasons.append("change_below_threshold")

    kpi_changes: dict[str, float] = {}
    for key, current in (current_kpis or {}).items():
        previous = (previous_kpis or {}).get(key)
        if isinstance(current, (int, float)) and isinstance(previous, (int, float)):
            denominator = max(abs(float(previous)), 1e-12)
            kpi_changes[str(key)] = round(
                (float(current) - float(previous)) / denominator * 100, 4
            )
    max_kpi_change_percent = max((abs(value) for value in kpi_changes.values()), default=None)
    if (
        policy["significant_kpi_change_percent"] > 0
        and previous_kpis
        and max_kpi_change_percent is not None
        and max_kpi_change_percent < policy["significant_kpi_change_percent"]
    ):
        reasons.append("kpi_change_below_threshold")

    eligible_time = _parse_datetime(last_eligible_at)
    if eligible_time and policy["cooldown_minutes"] > 0:
        elapsed_minutes = (now - eligible_time).total_seconds() / 60
        if elapsed_minutes < policy["cooldown_minutes"]:
            reasons.append("cooldown_active")

    alert_severities = [
        str(item.get("severity") or "warning").lower()
        for item in (quality_alerts or [])
        if isinstance(item, dict)
    ]
    severity = max(
        (item for item in alert_severities if item in SEVERITY_RANK),
        key=lambda item: SEVERITY_RANK[item],
        default="info",
    )
    if SEVERITY_RANK[severity] < SEVERITY_RANK[policy["minimum_severity"]]:
        reasons.append("severity_below_threshold")

    decision = "eligible" if not reasons else "suppressed"
    identity = {
        "fingerprint": fingerprint,
        "decision": decision,
        "reasons": sorted(reasons),
        "recipient": policy["recipient"],
        "channels": sorted(channels),
    }
    return {
        "decision": decision,
        "reason_codes": reasons,
        "severity": severity,
        "fingerprint": fingerprint,
        "decision_fingerprint": hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode()
        ).hexdigest(),
        "source_age_hours": (
            round(source_age_hours, 3) if source_age_hours is not None else None
        ),
        "row_change_percent": (
            round(row_change_percent, 4)
            if row_change_percent is not None
            else None
        ),
        "kpi_changes": kpi_changes,
        "max_kpi_change_percent": max_kpi_change_percent,
        "evaluated_at": now.isoformat(),
        "delivery_sent": False,
        "delivery_channels": sorted(channels),
    }
