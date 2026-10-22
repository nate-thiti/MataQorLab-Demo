"""Lease-based background worker for cron and on-upload ETL schedules."""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.supabase import get_supabase_client
from app.core.observability import bind_job_id, reset_job_id
from app.services.etl_execution import EtlExecutionError, execute_etl_recipe
from app.services.etl_schedule import calculate_next_run
from app.services.automation_guardrails import (
    evaluate_delivery_candidate,
    normalize_automation_config,
)
from app.services.scheduled_delivery import (
    ScheduledDeliveryError,
    create_narration,
    deterministic_narration,
    send_email_report,
)
from app.services.scheduled_chat_delivery import deliver_chat_report

logger = logging.getLogger("mataqorlab.worker.etl")


def build_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:10]}"


def claim_due_schedules(client: Any, worker_id: str) -> list[dict[str, Any]]:
    response = client.rpc(
        "claim_due_etl_schedules",
        {
            "p_worker_id": worker_id,
            "p_limit": settings.ETL_SCHEDULER_BATCH_SIZE,
            "p_lease_seconds": settings.ETL_SCHEDULER_LEASE_SECONDS,
        },
    ).execute()
    return response.data or []


def claim_schedule(client: Any, schedule_id: str, worker_id: str) -> dict[str, Any] | None:
    response = client.rpc(
        "claim_etl_schedule",
        {
            "p_schedule_id": schedule_id,
            "p_worker_id": worker_id,
            "p_lease_seconds": settings.ETL_SCHEDULER_LEASE_SECONDS,
        },
    ).execute()
    rows = response.data or []
    return rows[0] if rows else None


def _finish_schedule(
    client: Any,
    schedule: dict[str, Any],
    worker_id: str,
    *,
    result: dict[str, Any] | None = None,
    error: Exception | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    schedule_error = None
    try:
        next_run = calculate_next_run(
            str(schedule.get("schedule_kind") or "manual"),
            schedule.get("cron_expression"),
            str(schedule.get("timezone") or "UTC"),
            enabled=bool(schedule.get("enabled")),
            after=now,
        )
    except Exception as exc:
        next_run = None
        schedule_error = exc
        error = error or exc
    failed = error is not None
    update = {
        "next_run_at": next_run.isoformat() if next_run else None,
        "last_run_at": now.isoformat(),
        "last_status": "failed" if failed else "completed",
        "last_error": str(error or schedule_error)[:1000] if failed else None,
        "consecutive_failures": (
            int(schedule.get("consecutive_failures") or 0) + 1 if failed else 0
        ),
        "locked_at": None,
        "locked_by": None,
        "updated_at": now.isoformat(),
    }
    if result and result.get("run_id"):
        update["last_run_id"] = result["run_id"]
    if result and result.get("output_file"):
        update["latest_output_file"] = result["output_file"]
    if result and result.get("output_version"):
        update["latest_output_version"] = result["output_version"]
    if result and result.get("guardrail_decision"):
        config = normalize_automation_config(schedule.get("alert_config"))
        decision = result["guardrail_decision"]
        config["runtime"] = {
            **(config.get("runtime") or {}),
            "last_fingerprint": result.get("content_fingerprint"),
            "last_decision": decision,
            "last_kpi_snapshot": result.get("kpi_snapshot") or {},
            **(
                {"last_eligible_at": decision.get("evaluated_at")}
                if decision.get("decision") == "eligible"
                else {}
            ),
        }
        update["alert_config"] = config
    (
        client.table("etl_schedules")
        .update(update)
        .eq("id", schedule["id"])
        .eq("locked_by", worker_id)
        .execute()
    )


def _run_claimed_schedule(
    schedule: dict[str, Any],
    worker_id: str,
    *,
    client: Any | None = None,
    trigger_kind: str | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    previous_rows = None
    if schedule.get("last_run_id"):
        try:
            prior = (
                client.table("etl_pipeline_runs")
                .select("output_rows")
                .eq("id", schedule["last_run_id"])
                .limit(1)
                .execute()
            )
            previous_rows = (prior.data or [{}])[0].get("output_rows")
        except Exception:
            previous_rows = None
    try:
        result = execute_etl_recipe(
            str(schedule["user_id"]),
            str(schedule["recipe_id"]),
            output_name=schedule.get("output_name"),
            schedule_id=str(schedule["id"]),
            output_dataset_key=schedule.get("output_dataset_key"),
            trigger_kind=trigger_kind or str(schedule.get("schedule_kind") or "manual"),
            client=client,
        )
        config = normalize_automation_config(schedule.get("alert_config"))
        runtime = config.get("runtime") or {}
        delivery_channels = []
        if config.get("delivery_enabled"):
            delivery_channels.append("email")
        if schedule.get("chat_delivery_enabled"):
            delivery_channels.append("chat")
        decision = evaluate_delivery_candidate(
            config=config,
            data_contract=result.get("data_contract"),
            fingerprint=str(result.get("content_fingerprint") or ""),
            previous_fingerprint=runtime.get("last_fingerprint"),
            current_rows=int(result.get("rows") or 0),
            previous_rows=previous_rows,
            source_updated_at=(result.get("metrics") or {}).get("source_updated_at"),
            quality_alerts=result.get("quality_alerts") or [],
            current_kpis=result.get("kpi_snapshot") or {},
            previous_kpis=runtime.get("last_kpi_snapshot") or {},
            last_eligible_at=runtime.get("last_eligible_at"),
            delivery_channels=delivery_channels,
            chat_target_valid=bool(schedule.get("chat_target_conversation_id")),
        )
        result["guardrail_decision"] = decision
        try:
            client.table("automation_delivery_events").insert(
                {
                    "user_id": schedule["user_id"],
                    "schedule_id": schedule["id"],
                    "run_id": result.get("run_id"),
                    "event_type": decision["decision"],
                    "severity": decision["severity"],
                    "fingerprint": decision["decision_fingerprint"],
                    "reason_codes": decision["reason_codes"],
                    "metrics": result.get("metrics") or {},
                }
            ).execute()
        except Exception as exc:
            logger.warning(
                "automation_telemetry_unavailable",
                extra={"schedule_id": schedule.get("id"), "error_code": "dependency_unavailable", "error": str(exc)},
            )
        if decision["decision"] == "eligible":
            evidence = {
                "rows": result.get("rows"),
                "kpis": result.get("kpi_snapshot") or {},
                "kpi_changes": decision.get("kpi_changes") or {},
                "quality_alerts": result.get("quality_alerts") or [],
                "source_age_hours": decision.get("source_age_hours"),
                "data_contract": {
                    "period_status": (result.get("data_contract") or {}).get("period_status"),
                    "metric_definition": (result.get("data_contract") or {}).get("metric_definition"),
                },
            }
            narration, llm_tokens, narration_model = create_narration(
                evidence,
                config.get("locale") or "th",
                schedule.get("chat_delivery_prompt"),
            ) if config.get("ai_narration_enabled", True) else (
                deterministic_narration(evidence, config.get("locale") or "th"),
                0,
                "disabled",
            )
            result.setdefault("metrics", {})
            result["metrics"]["llm_tokens"] = llm_tokens

            if "chat" in delivery_channels:
                try:
                    chat_delivery = deliver_chat_report(
                        client=client,
                        user_id=str(schedule["user_id"]),
                        schedule_id=str(schedule["id"]),
                        run_id=result.get("run_id"),
                        fingerprint=str(result.get("content_fingerprint") or ""),
                        narration=narration,
                        metadata={
                            "dataset_key": schedule.get("chat_source_dataset_key"),
                            "output_dataset_key": result.get("dataset_key"),
                            "evidence": evidence,
                            "narration_model": narration_model,
                        },
                    )
                    decision["delivery_sent"] = True
                    result["metrics"]["chat_deliveries"] = (
                        1 if chat_delivery.get("created") else 0
                    )
                    client.table("automation_delivery_events").insert({
                        "user_id": schedule["user_id"],
                        "schedule_id": schedule["id"],
                        "run_id": result.get("run_id"),
                        "event_type": "delivered",
                        "severity": decision["severity"],
                        "fingerprint": decision["decision_fingerprint"],
                        "reason_codes": [],
                        "metrics": {
                            **(result.get("metrics") or {}),
                            **chat_delivery,
                            "narration_model": narration_model,
                        },
                        "delivery_channel": "chat",
                        "delivered_at": datetime.now(timezone.utc).isoformat(),
                        "narration": narration,
                    }).execute()
                except Exception as exc:
                    decision["chat_delivery_error"] = str(exc)[:500]
                    try:
                        client.table("automation_delivery_events").insert({
                            "user_id": schedule["user_id"],
                            "schedule_id": schedule["id"],
                            "run_id": result.get("run_id"),
                            "event_type": "failed",
                            "severity": decision["severity"],
                            "fingerprint": decision["decision_fingerprint"],
                            "reason_codes": ["delivery_failed"],
                            "metrics": {
                                **(result.get("metrics") or {}),
                                "narration_model": narration_model,
                            },
                            "delivery_channel": "chat",
                            "error_message": str(exc)[:1000],
                            "narration": narration,
                        }).execute()
                    except Exception as telemetry_exc:
                        logger.warning(
                            "chat_failure_telemetry_unavailable",
                            extra={"schedule_id": schedule.get("id"), "error_code": "dependency_unavailable", "error": str(telemetry_exc)},
                        )

            if "email" in delivery_channels:
                tracking_token = str(uuid.uuid4())
                tracking_url = None
                if settings.DELIVERY_PUBLIC_BASE_URL:
                    tracking_url = (
                        settings.DELIVERY_PUBLIC_BASE_URL.rstrip("/")
                        + f"/api/v1/automation/delivery/open/{tracking_token}"
                    )
                try:
                    delivery = send_email_report(
                        recipient=config["recipient"],
                        subject=f"MataQorLab · {schedule.get('output_name') or 'Scheduled report'}",
                        narration=narration,
                        tracking_url=tracking_url,
                    )
                    decision["delivery_sent"] = True
                    result["metrics"]["email_deliveries"] = 1
                    client.table("automation_delivery_events").insert({
                        "user_id": schedule["user_id"],
                        "schedule_id": schedule["id"],
                        "run_id": result.get("run_id"),
                        "event_type": "delivered",
                        "severity": decision["severity"],
                        "fingerprint": decision["decision_fingerprint"],
                        "reason_codes": [],
                        "metrics": {
                            **(result.get("metrics") or {}),
                            **delivery,
                            "narration_model": narration_model,
                        },
                        "delivery_token": tracking_token,
                        "delivery_channel": "email",
                        "delivered_at": datetime.now(timezone.utc).isoformat(),
                        "narration": narration,
                    }).execute()
                except Exception as exc:
                    decision["email_delivery_error"] = str(exc)[:500]
                    try:
                        client.table("automation_delivery_events").insert({
                            "user_id": schedule["user_id"],
                            "schedule_id": schedule["id"],
                            "run_id": result.get("run_id"),
                            "event_type": "failed",
                            "severity": decision["severity"],
                            "fingerprint": decision["decision_fingerprint"],
                            "reason_codes": ["delivery_failed"],
                            "metrics": {
                                **(result.get("metrics") or {}),
                                "narration_model": narration_model,
                                "llm_tokens": llm_tokens,
                            },
                            "delivery_channel": "email",
                            "error_message": str(exc)[:1000],
                            "narration": narration,
                        }).execute()
                    except Exception as telemetry_exc:
                        logger.warning(
                            "delivery_failure_telemetry_unavailable",
                            extra={"schedule_id": schedule.get("id"), "error_code": "dependency_unavailable", "error": str(telemetry_exc)},
                        )
                    if not isinstance(exc, ScheduledDeliveryError):
                        logger.exception(
                            "scheduled_delivery_failed",
                            extra={"schedule_id": schedule.get("id"), "error_code": "scheduler_failed"},
                        )
    except Exception as exc:
        _finish_schedule(client, schedule, worker_id, error=exc)
        if isinstance(exc, EtlExecutionError):
            raise
        raise EtlExecutionError(str(exc)) from exc
    _finish_schedule(client, schedule, worker_id, result=result)
    return result


def run_claimed_schedule(
    schedule: dict[str, Any],
    worker_id: str,
    *,
    client: Any | None = None,
    trigger_kind: str | None = None,
) -> dict[str, Any]:
    token = bind_job_id(f"etl:{schedule.get('id')}")
    try:
        logger.info(
            "etl_job_started",
            extra={"schedule_id": schedule.get("id"), "worker_id": worker_id},
        )
        result = _run_claimed_schedule(
            schedule,
            worker_id,
            client=client,
            trigger_kind=trigger_kind,
        )
        logger.info(
            "etl_job_completed",
            extra={"schedule_id": schedule.get("id"), "worker_id": worker_id, "run_id": result.get("run_id")},
        )
        return result
    except Exception:
        logger.exception(
            "etl_job_failed",
            extra={"schedule_id": schedule.get("id"), "worker_id": worker_id, "error_code": "scheduler_failed"},
        )
        raise
    finally:
        reset_job_id(token)


def run_schedule_now(
    schedule_id: str,
    *,
    client: Any | None = None,
    worker_id: str | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    worker_id = worker_id or f"manual:{build_worker_id()}"
    schedule = claim_schedule(client, schedule_id, worker_id)
    if not schedule:
        raise EtlExecutionError("Schedule is already running")
    return run_claimed_schedule(
        schedule,
        worker_id,
        client=client,
        trigger_kind="manual",
    )


def run_on_upload_schedules(user_id: str, dataset_key: str) -> list[dict[str, Any]]:
    """Run enabled on-upload schedules whose saved recipe targets this dataset."""
    client = get_supabase_client()
    response = (
        client.table("etl_schedules")
        .select("*, etl_recipes!inner(dataset_key)")
        .eq("user_id", user_id)
        .eq("enabled", True)
        .eq("schedule_kind", "on_upload")
        .eq("etl_recipes.dataset_key", dataset_key)
        .execute()
    )
    results: list[dict[str, Any]] = []
    for item in response.data or []:
        worker_id = f"upload:{build_worker_id()}"
        claimed = claim_schedule(client, str(item["id"]), worker_id)
        if not claimed:
            continue
        try:
            results.append(
                run_claimed_schedule(
                    claimed,
                    worker_id,
                    client=client,
                    trigger_kind="on_upload",
                )
            )
        except EtlExecutionError:
            continue
    return results


async def scheduler_loop(stop_event: asyncio.Event) -> None:
    """Poll and execute due jobs until application shutdown."""
    worker_id = f"cron:{build_worker_id()}"
    poll_seconds = max(5, int(settings.ETL_SCHEDULER_POLL_SECONDS))
    while not stop_event.is_set():
        try:
            client = get_supabase_client()
            schedules = await asyncio.to_thread(claim_due_schedules, client, worker_id)
            for schedule in schedules:
                if stop_event.is_set():
                    break
                try:
                    await asyncio.to_thread(
                        run_claimed_schedule,
                        schedule,
                        worker_id,
                        client=client,
                    )
                except EtlExecutionError as exc:
                    logger.error(
                        "scheduled_etl_failed",
                        extra={"schedule_id": schedule.get("id"), "error_code": "scheduler_failed", "error": str(exc)},
                    )
        except Exception as exc:
            logger.exception(
                "scheduled_etl_poll_failed",
                extra={"error_code": "dependency_unavailable", "error": str(exc)},
            )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except asyncio.TimeoutError:
            pass
