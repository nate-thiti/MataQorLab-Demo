"""Lease-based deterministic Smart Alert evaluator and delivery worker."""
from __future__ import annotations

import asyncio
import logging
import hashlib
import math
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import requests

from app.core.config import settings
from app.core.supabase import get_supabase_client
from app.core.observability import bind_job_id, reset_job_id
from app.services.scheduled_delivery import send_email_report
from app.services.visualizations import VisualizationError, generate_dashboard

logger = logging.getLogger("mataqorlab.worker.smart_alert")


class SmartAlertError(RuntimeError):
    """A rule could not be evaluated or delivered safely."""


def build_alert_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:10]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normal_metric_key(value: Any) -> str:
    return "".join(character for character in str(value or "").casefold() if character.isalnum())


def extract_metric_value(
    dashboard: dict[str, Any],
    metric_key: str,
) -> tuple[float, dict[str, Any]]:
    """Resolve one exact dashboard KPI without guessing across multiple metrics."""
    requested = _normal_metric_key(metric_key)
    if not requested:
        raise SmartAlertError("Metric key is required")
    matches: list[dict[str, Any]] = []
    for kpi in dashboard.get("kpis") or []:
        if not isinstance(kpi, dict):
            continue
        aliases = {
            _normal_metric_key(kpi.get("label")),
            _normal_metric_key(kpi.get("field")),
            _normal_metric_key(
                f"{kpi.get('kind')}:{kpi.get('field') or 'rows'}"
            ),
        }
        if kpi.get("kind") == "count":
            aliases.update({"rows", "rowcount", "count"})
        if requested in aliases:
            matches.append(kpi)
    if len(matches) != 1:
        available = sorted(
            {
                str(kpi.get("label") or kpi.get("field") or "")
                for kpi in dashboard.get("kpis") or []
                if isinstance(kpi, dict)
            }
        )
        detail = ", ".join(item for item in available if item)[:500]
        if not matches:
            raise SmartAlertError(
                f"Metric '{metric_key}' was not found. Available KPIs: {detail or 'none'}"
            )
        raise SmartAlertError(f"Metric '{metric_key}' is ambiguous")
    raw_value = matches[0].get("value")
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise SmartAlertError(f"Metric '{metric_key}' is not numeric") from exc
    if not math.isfinite(value):
        raise SmartAlertError(f"Metric '{metric_key}' is not finite")
    return value, matches[0]


def evaluate_condition(
    operator: str,
    current_value: float,
    threshold: float | None,
    previous_value: float | None,
) -> tuple[bool, float | None, str]:
    """Return match, comparison value and an evidence reason."""
    if threshold is None:
        raise SmartAlertError("Alert threshold is required")
    threshold_value = float(threshold)
    if operator == "gt":
        return current_value > threshold_value, current_value, "threshold_comparison"
    if operator == "gte":
        return current_value >= threshold_value, current_value, "threshold_comparison"
    if operator == "lt":
        return current_value < threshold_value, current_value, "threshold_comparison"
    if operator == "lte":
        return current_value <= threshold_value, current_value, "threshold_comparison"
    if operator == "eq":
        return current_value == threshold_value, current_value, "threshold_comparison"
    if operator not in {"change_gt", "change_lt"}:
        raise SmartAlertError("Unsupported alert operator")
    if previous_value is None:
        return False, None, "baseline_recorded"
    previous = float(previous_value)
    if previous == 0:
        return False, None, "zero_baseline"
    change_percent = ((current_value - previous) / abs(previous)) * 100
    if operator == "change_gt":
        return (
            abs(change_percent) > abs(threshold_value),
            change_percent,
            "absolute_change_percent",
        )
    return (
        change_percent < -abs(threshold_value),
        change_percent,
        "decrease_percent",
    )


def claim_due_alert_rules(client: Any, worker_id: str) -> list[dict[str, Any]]:
    response = client.rpc(
        "claim_due_customer_alert_rules",
        {
            "p_worker_id": worker_id,
            "p_limit": settings.SMART_ALERT_BATCH_SIZE,
            "p_lease_seconds": settings.SMART_ALERT_LEASE_SECONDS,
        },
    ).execute()
    return response.data or []


def claim_alert_rule(
    client: Any,
    rule_id: str,
    user_id: str,
    worker_id: str,
) -> dict[str, Any] | None:
    response = client.rpc(
        "claim_customer_alert_rule",
        {
            "p_rule_id": rule_id,
            "p_user_id": user_id,
            "p_worker_id": worker_id,
            "p_lease_seconds": settings.SMART_ALERT_LEASE_SECONDS,
        },
    ).execute()
    rows = response.data or []
    return rows[0] if rows else None


def _evaluate_metric(
    client: Any,
    rule: dict[str, Any],
) -> tuple[float, dict[str, Any], dict[str, Any]]:
    report_id = str(rule.get("report_id") or "")
    if not report_id:
        raise SmartAlertError("Alert must be linked to a dashboard")
    try:
        dashboard = generate_dashboard(
            str(rule["user_id"]),
            report_id,
            filters=rule.get("filter_state") or {},
            persist=False,
            client=client,
        )
    except VisualizationError as exc:
        raise SmartAlertError(str(exc)) from exc
    value, metric = extract_metric_value(dashboard, str(rule.get("metric_key") or ""))
    return value, metric, dashboard


def _https_webhook(value: str, channel: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise SmartAlertError(f"{channel} webhook must be an HTTPS server-side URL")
    return value


def _post_webhook(channel: str, url: str, message: str, evidence: dict[str, Any]) -> dict[str, Any]:
    endpoint = _https_webhook(url, channel)
    last_error: Exception | None = None
    for attempt in range(1, max(1, settings.SMART_ALERT_DELIVERY_ATTEMPTS) + 1):
        try:
            response = requests.post(
                endpoint,
                json={"text": message, "evidence": evidence},
                timeout=settings.SMART_ALERT_DELIVERY_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return {"status": "delivered", "attempts": attempt}
        except requests.RequestException as exc:
            last_error = exc
    raise SmartAlertError(f"{channel} delivery failed: {last_error}")


def dispatch_alert(
    rule: dict[str, Any],
    *,
    current_value: float,
    comparison_value: float | None,
) -> tuple[dict[str, Any], list[str]]:
    """Dispatch configured channels; URLs and SMTP credentials stay server-side."""
    message = (
        f"MataQorLab Smart Alert · {rule.get('name')}: "
        f"{rule.get('metric_key')} = {current_value:g}"
    )
    evidence = {
        "rule_id": rule.get("id"),
        "report_id": rule.get("report_id"),
        "metric_key": rule.get("metric_key"),
        "metric_value": current_value,
        "comparison_value": comparison_value,
        "operator": rule.get("operator"),
        "threshold": rule.get("threshold"),
    }
    results: dict[str, Any] = {}
    errors: list[str] = []
    channels = set(rule.get("channels") or ["in_app"])
    if "in_app" in channels:
        results["in_app"] = {"status": "delivered"}
    if "email" in channels:
        recipients = [
            str(value).strip()
            for value in rule.get("recipients") or []
            if "@" in str(value)
        ]
        if not recipients:
            errors.append("email: no recipient configured")
        else:
            deliveries = []
            for recipient in recipients:
                try:
                    deliveries.append(
                        send_email_report(
                            recipient=recipient,
                            subject=f"MataQorLab Smart Alert · {rule.get('name')}",
                            narration=message,
                        )
                    )
                except Exception as exc:
                    errors.append(f"email {recipient}: {str(exc)[:300]}")
            results["email"] = {
                "status": "delivered" if deliveries and not any(
                    error.startswith("email ") for error in errors
                ) else "failed",
                "delivered": deliveries,
            }
    webhook_settings = {
        "slack": settings.SMART_ALERT_SLACK_WEBHOOK_URL,
        "teams": settings.SMART_ALERT_TEAMS_WEBHOOK_URL,
        "webhook": settings.SMART_ALERT_WEBHOOK_URL,
    }
    for channel, url in webhook_settings.items():
        if channel not in channels:
            continue
        if not url:
            errors.append(f"{channel}: server-side webhook is not configured")
            results[channel] = {"status": "failed"}
            continue
        try:
            results[channel] = _post_webhook(channel, url, message, evidence)
        except SmartAlertError as exc:
            errors.append(str(exc)[:500])
            results[channel] = {"status": "failed"}
    return results, errors


def _evaluation_key(rule: dict[str, Any]) -> str:
    due = rule.get("next_evaluation_at") or rule.get("locked_at") or "manual"
    return hashlib.sha256(f"{rule.get('id')}:{due}".encode("utf-8")).hexdigest()


def _finish_rule(
    client: Any,
    rule: dict[str, Any],
    worker_id: str,
    *,
    current_value: float | None,
    status: str,
    error: str | None = None,
    triggered: bool = False,
) -> None:
    now = _now()
    interval = min(1440, max(1, int(rule.get("evaluation_interval_minutes") or 5)))
    failed = bool(error)
    update = {
        "last_evaluated_at": now.isoformat(),
        "next_evaluation_at": (now + timedelta(minutes=interval)).isoformat(),
        "last_status": "failed" if failed else status,
        "last_error": error[:2000] if error else None,
        "consecutive_failures": (
            int(rule.get("consecutive_failures") or 0) + 1 if failed else 0
        ),
        "locked_at": None,
        "locked_by": None,
        "updated_at": now.isoformat(),
    }
    if current_value is not None:
        update["last_value"] = current_value
    if triggered:
        update["last_triggered_at"] = now.isoformat()
    (
        client.table("customer_alert_rules")
        .update(update)
        .eq("id", rule["id"])
        .eq("locked_by", worker_id)
        .execute()
    )


def _run_claimed_alert_rule(
    rule: dict[str, Any],
    worker_id: str,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    current_value: float | None = None
    try:
        current_value, metric, dashboard = _evaluate_metric(client, rule)
        previous = (
            float(rule["last_value"]) if rule.get("last_value") is not None else None
        )
        matched, comparison_value, comparison_reason = evaluate_condition(
            str(rule.get("operator") or ""),
            current_value,
            float(rule["threshold"]) if rule.get("threshold") is not None else None,
            previous,
        )
        if not matched:
            status = "baseline" if comparison_reason in {"baseline_recorded", "zero_baseline"} else "not_triggered"
            _finish_rule(
                client,
                rule,
                worker_id,
                current_value=current_value,
                status=status,
            )
            return {
                "rule_id": rule["id"],
                "status": status,
                "metric_value": current_value,
                "comparison_value": comparison_value,
                "reason": comparison_reason,
            }

        now = _now()
        muted_until = _parse_datetime(rule.get("muted_until"))
        last_triggered = _parse_datetime(rule.get("last_triggered_at"))
        cooldown = timedelta(minutes=int(rule.get("cooldown_minutes") or 60))
        suppression_reason = None
        if muted_until and muted_until > now:
            suppression_reason = "muted"
        elif last_triggered and now - last_triggered < cooldown:
            suppression_reason = "cooldown"

        key = _evaluation_key(rule)
        existing = (
            client.table("customer_alert_events")
            .select("id,status,delivery_results")
            .eq("evaluation_key", key)
            .limit(1)
            .execute()
            .data
            or []
        )
        if existing:
            prior = existing[0]
            _finish_rule(
                client,
                rule,
                worker_id,
                current_value=current_value,
                status=str(prior.get("status") or "delivered"),
                triggered=prior.get("status") in {"triggered", "delivered", "failed"},
            )
            return {
                "rule_id": rule["id"],
                "event_id": prior.get("id"),
                "status": prior.get("status"),
                "idempotent_replay": True,
            }

        event_status = "suppressed" if suppression_reason else "triggered"
        event = (
            client.table("customer_alert_events")
            .insert(
                {
                    "rule_id": rule["id"],
                    "user_id": rule["user_id"],
                    "status": event_status,
                    "metric_value": current_value,
                    "previous_value": previous,
                    "comparison_value": comparison_value,
                    "reason": suppression_reason or comparison_reason,
                    "evaluation_key": key,
                    "evidence": {
                        "metric": metric,
                        "operator": rule.get("operator"),
                        "threshold": rule.get("threshold"),
                        "filter_state": rule.get("filter_state") or {},
                        "report_id": rule.get("report_id"),
                        "row_count": dashboard.get("row_count"),
                        "aggregation_scope": dashboard.get("aggregation_scope"),
                    },
                }
            )
            .execute()
            .data
            or [{}]
        )[0]
        if suppression_reason:
            _finish_rule(
                client,
                rule,
                worker_id,
                current_value=current_value,
                status="suppressed",
            )
            return {
                "rule_id": rule["id"],
                "event_id": event.get("id"),
                "status": "suppressed",
                "reason": suppression_reason,
            }

        delivery_results, delivery_errors = dispatch_alert(
            rule,
            current_value=current_value,
            comparison_value=comparison_value,
        )
        delivered = not delivery_errors
        final_status = "delivered" if delivered else "failed"
        (
            client.table("customer_alert_events")
            .update(
                {
                    "status": final_status,
                    "delivery_results": delivery_results,
                    "reason": (
                        comparison_reason
                        if delivered
                        else "; ".join(delivery_errors)[:1000]
                    ),
                }
            )
            .eq("id", event.get("id"))
            .eq("rule_id", rule["id"])
            .execute()
        )
        error = "; ".join(delivery_errors) if delivery_errors else None
        _finish_rule(
            client,
            rule,
            worker_id,
            current_value=current_value,
            status=final_status,
            error=error,
            triggered=True,
        )
        return {
            "rule_id": rule["id"],
            "event_id": event.get("id"),
            "status": final_status,
            "metric_value": current_value,
            "comparison_value": comparison_value,
            "delivery_results": delivery_results,
            "errors": delivery_errors,
        }
    except Exception as exc:
        error = str(exc)[:2000]
        _finish_rule(
            client,
            rule,
            worker_id,
            current_value=current_value,
            status="failed",
            error=error,
        )
        if isinstance(exc, SmartAlertError):
            raise
        raise SmartAlertError(error) from exc


def run_claimed_alert_rule(
    rule: dict[str, Any],
    worker_id: str,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    token = bind_job_id(f"smart-alert:{rule.get('id')}")
    try:
        logger.info(
            "smart_alert_job_started",
            extra={"rule_id": rule.get("id"), "worker_id": worker_id},
        )
        result = _run_claimed_alert_rule(rule, worker_id, client=client)
        logger.info(
            "smart_alert_job_completed",
            extra={"rule_id": rule.get("id"), "worker_id": worker_id, "status": result.get("status")},
        )
        return result
    except Exception:
        logger.exception(
            "smart_alert_job_failed",
            extra={"rule_id": rule.get("id"), "worker_id": worker_id, "error_code": "scheduler_failed"},
        )
        raise
    finally:
        reset_job_id(token)


def run_alert_rule_now(
    user_id: str,
    rule_id: str,
    *,
    client: Any | None = None,
    worker_id: str | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    worker_id = worker_id or f"manual:{build_alert_worker_id()}"
    rule = claim_alert_rule(client, rule_id, user_id, worker_id)
    if not rule:
        raise SmartAlertError(
            "Alert is disabled, missing a dashboard, or already being evaluated"
        )
    return run_claimed_alert_rule(rule, worker_id, client=client)


async def smart_alert_scheduler_loop(stop_event: asyncio.Event) -> None:
    """Poll and evaluate due Smart Alerts until application shutdown."""
    worker_id = f"smart-alert:{build_alert_worker_id()}"
    poll_seconds = max(5, int(settings.SMART_ALERT_POLL_SECONDS))
    while not stop_event.is_set():
        try:
            client = get_supabase_client()
            rules = await asyncio.to_thread(claim_due_alert_rules, client, worker_id)
            for rule in rules:
                if stop_event.is_set():
                    break
                try:
                    await asyncio.to_thread(
                        run_claimed_alert_rule,
                        rule,
                        worker_id,
                        client=client,
                    )
                except SmartAlertError as exc:
                    logger.error(
                        "smart_alert_failed",
                        extra={"rule_id": rule.get("id"), "error_code": "scheduler_failed", "error": str(exc)},
                    )
        except Exception as exc:
            logger.exception(
                "smart_alert_poll_failed",
                extra={"error_code": "dependency_unavailable", "error": str(exc)},
            )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except asyncio.TimeoutError:
            pass
