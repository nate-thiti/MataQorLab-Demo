"""Reusable ETL execution used by HTTP requests and the schedule worker."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from typing import Any

from app.core.supabase import get_supabase_client
from app.services.dataset_engine import DatasetHandle, TABLE_NAME
from app.services.dataset_loader import load_handle_from_storage
from app.services.etl_pipeline import normalize_recipe, validate_data_contract
from app.services.storage_quota import enforce_customer_storage_quota
from app.services.automation_guardrails import fingerprint_file
from app.services.storage_download import get_storage_object_metadata
from app.core.config import settings


logger = logging.getLogger("mataqorlab.etl_execution")


class EtlExecutionError(RuntimeError):
    """An ETL run failed after its audit record was created."""


def _insert_pipeline_run(client: Any, payload: dict[str, Any]):
    try:
        return client.table("etl_pipeline_runs").insert(payload).execute()
    except Exception as exc:
        if (
            payload.get("trigger_kind") != "data_setup"
            or "etl_pipeline_runs_trigger_kind_check" not in str(exc)
        ):
            raise
        legacy_payload = {
            **payload,
            "trigger_kind": "manual",
            "recipe_snapshot": {
                **dict(payload.get("recipe_snapshot") or {}),
                "_requested_trigger_kind": "data_setup",
            },
        }
        logger.warning(
            "etl_legacy_trigger_kind_fallback",
            extra={"error_code": "legacy_trigger_kind_constraint"},
        )
        return client.table("etl_pipeline_runs").insert(legacy_payload).execute()


def build_semantic_kpi_snapshot(handle: DatasetHandle, mapping: dict[str, str]) -> dict[str, float]:
    """Compute a small deterministic KPI packet without exposing raw rows."""
    columns_by_role: dict[str, str] = {}
    available = set(handle.column_names())
    for column, role in mapping.items():
        normalized = str(role or "").strip().lower()
        if column in available and normalized and normalized not in columns_by_role:
            columns_by_role[normalized] = column

    def quote(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    snapshot: dict[str, float] = {"rows": float(handle.row_count())}
    for role, key in (
        ("sales", "revenue"),
        ("revenue", "revenue"),
        ("cost", "cost"),
        ("profit", "profit"),
        ("qty", "quantity"),
        ("quantity", "quantity"),
    ):
        column = columns_by_role.get(role)
        if column and key not in snapshot:
            value = handle._con.execute(
                f"SELECT COALESCE(SUM(TRY_CAST({quote(column)} AS DOUBLE)), 0) FROM {TABLE_NAME}"
            ).fetchone()[0]
            snapshot[key] = round(float(value or 0), 6)
    for role, key in (("order_id", "orders"), ("customer_id", "customers")):
        column = columns_by_role.get(role)
        if column:
            value = handle._con.execute(
                f"SELECT COUNT(DISTINCT {quote(column)}) FROM {TABLE_NAME}"
            ).fetchone()[0]
            snapshot[key] = float(value or 0)
    if "profit" not in snapshot and "revenue" in snapshot and "cost" in snapshot:
        snapshot["profit"] = round(snapshot["revenue"] - snapshot["cost"], 6)
    if snapshot.get("revenue"):
        snapshot["gross_margin_percent"] = round(
            snapshot.get("profit", 0) / snapshot["revenue"] * 100, 6
        )
    return snapshot


def build_output_dataset_key(schedule_id: str) -> str:
    """Stable identity used by Chat/Visualization across ETL output versions."""
    return f"etl:{schedule_id}"


def build_output_file_names(
    output_dataset_key: str,
    output_name: str | None,
    source_dataset_key: str,
    version: str,
) -> tuple[str, str]:
    """Return a stable canonical file plus an immutable audit version."""
    base_name = output_name or source_dataset_key.rsplit(".", 1)[0]
    stem = re.sub(
        r"[^A-Za-z0-9_\-\u0E00-\u0E7F]",
        "_",
        base_name,
    ).strip("_") or "scheduled_etl"
    identity_hash = hashlib.sha256(output_dataset_key.encode("utf-8")).hexdigest()[:20]
    return (
        f"etl_dataset_{identity_hash}.parquet",
        f"etl_{stem}_v{version}.parquet",
    )


def create_etl_run(
    client: Any,
    *,
    user_id: str,
    recipe_id: str,
    dataset_key: str,
    output_dataset_key: str,
    recipe: dict[str, Any],
    trigger_kind: str = "manual",
    schedule_id: str | None = None,
) -> Any:
    """Insert a running etl_pipeline_runs row and return its id."""
    run_response = _insert_pipeline_run(
        client,
        {
            "user_id": user_id,
            "recipe_id": recipe_id,
            "schedule_id": schedule_id,
            "trigger_kind": trigger_kind,
            "dataset_key": dataset_key,
            "output_dataset_key": output_dataset_key,
            "status": "running",
            "recipe_snapshot": recipe,
        },
    )
    return (run_response.data or [{}])[0].get("id")


def publish_transformed_handle(
    client: Any,
    *,
    user_id: str,
    handle: DatasetHandle,
    run_id: Any,
    recipe: dict[str, Any],
    dataset_key: str,
    output_dataset_key: str,
    output_name: str | None,
    contract_readiness: dict[str, Any],
    source_dataset_key: str,
    started_monotonic: float | None = None,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write parquet outputs and complete the ETL run audit record.

    Ownership: publication / materialization only.
    Does not load sources, clean, or map.
    """
    temp_path: str | None = None
    started = started_monotonic if started_monotonic is not None else time.monotonic()
    source_metadata = source_metadata or {}
    mapping = recipe.get("column_mapping") or {}
    try:
        preflight_quality_alerts = (
            (handle._cleaning_report or {})
            .get("recipe_audit", {})
            .get("quality_alerts", [])
        )
        if (
            (recipe.get("data_contract") or {}).get("enforcement_mode") == "strict"
            and any(
                alert.get("severity") == "critical"
                for alert in preflight_quality_alerts
            )
        ):
            failed_rules = ", ".join(
                sorted({
                    str(alert.get("type") or "quality_rule")
                    for alert in preflight_quality_alerts
                    if alert.get("severity") == "critical"
                })
            )
            raise EtlExecutionError(
                f"Strict data contract quality checks failed: {failed_rules}"
            )

        export_handle = DatasetHandle.for_sql_execution(handle)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            temp_path = tmp.name
        escaped = temp_path.replace("'", "''")
        export_handle._con.execute(
            f"COPY (SELECT * FROM {TABLE_NAME}) TO '{escaped}' "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        output_bytes = os.path.getsize(temp_path)
        content_fingerprint = fingerprint_file(temp_path)

        version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        canonical_name, published_name = build_output_file_names(
            output_dataset_key,
            output_name,
            source_dataset_key,
            version,
        )
        version_path = f"{user_id}/{published_name}"
        with open(temp_path, "rb") as upload_file:
            enforce_customer_storage_quota(
                user_id,
                os.path.getsize(temp_path),
                version_path,
            )
            client.storage.from_("business-data").upload(
                path=version_path,
                file=upload_file,
                file_options={
                    "content-type": "application/octet-stream",
                    "upsert": "false",
                },
            )
        canonical_path = f"{user_id}/{canonical_name}"
        with open(temp_path, "rb") as upload_file:
            enforce_customer_storage_quota(
                user_id,
                os.path.getsize(temp_path),
                canonical_path,
            )
            client.storage.from_("business-data").upload(
                path=canonical_path,
                file=upload_file,
                file_options={
                    "content-type": "application/octet-stream",
                    "cache-control": "0",
                    "upsert": "true",
                },
            )

        report = dict(handle._cleaning_report or {})
        quality_alerts = list(
            report.get("recipe_audit", {}).get("quality_alerts", [])
        )
        if contract_readiness["status"] != "ready":
            quality_alerts.append({
                "column": "dataset",
                "type": "data_contract_readiness",
                "severity": (
                    "critical"
                    if contract_readiness["status"] == "invalid"
                    else "warning"
                ),
                "status": contract_readiness["status"],
                "score": contract_readiness["score"],
                "missing": contract_readiness["missing"],
                "errors": contract_readiness["errors"],
            })
        report["data_contract_readiness"] = contract_readiness
        kpi_snapshot = build_semantic_kpi_snapshot(handle, mapping)
        execution_metrics = {
            "duration_ms": round((time.monotonic() - started) * 1000),
            "output_bytes": output_bytes,
            "llm_tokens": 0,
            "email_deliveries": 0,
            "source_updated_at": source_metadata.get("updated_at"),
            "source_bytes": source_metadata.get("size"),
        }
        report["automation_metrics"] = execution_metrics
        completed_at = datetime.now(timezone.utc).isoformat()
        if run_id:
            (
                client.table("etl_pipeline_runs")
                .update(
                    {
                        "status": "completed",
                        "input_rows": report.get("rows_before"),
                        "output_rows": handle.row_count(),
                        "output_dataset_key": output_dataset_key,
                        "output_version": published_name,
                        "report": report,
                        "completed_at": completed_at,
                    }
                )
                .eq("id", run_id)
                .eq("user_id", user_id)
                .execute()
            )
            for alert in quality_alerts:
                client.table("etl_quality_alerts").insert(
                    {
                        "user_id": user_id,
                        "run_id": run_id,
                        "dataset_key": dataset_key,
                        "severity": alert.get("severity", "warning"),
                        "rule_key": (
                            f"{alert.get('column', 'dataset')}:"
                            f"{alert.get('type', 'quality')}"
                        ),
                        "detail": alert,
                    }
                ).execute()
        return {
            "ok": True,
            "run_id": run_id,
            "dataset_key": output_dataset_key,
            "output_file": canonical_name,
            "output_version": published_name,
            "rows": handle.row_count(),
            "quality_alerts": quality_alerts,
            "content_fingerprint": content_fingerprint,
            "data_contract": recipe.get("data_contract") or {},
            "metrics": execution_metrics,
            "kpi_snapshot": kpi_snapshot,
        }
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def execute_etl_recipe(
    user_id: str,
    recipe_id: str,
    *,
    output_name: str | None = None,
    schedule_id: str | None = None,
    output_dataset_key: str | None = None,
    trigger_kind: str = "manual",
    client: Any | None = None,
) -> dict[str, Any]:
    """Execute one saved recipe and persist its run, output and quality alerts.

    Architectural boundary (Phase 4.5):
      - Schedule/manual existing ETL → this function (legacy path)
      - Data Setup workflow → WorkflowEngine only

    Do **not** use ``execute_etl_recipe`` from a future AI Orchestrator to
    bypass WorkflowEngine for setup operations. Schedule/manual path still uses
    prepare_for_analysis (clean + map coerce + contract) as a single convenience
    transform, then publish_transformed_handle.
    """
    client = client or get_supabase_client()
    recipe_response = (
        client.table("etl_recipes")
        .select("*")
        .eq("id", recipe_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not recipe_response.data:
        raise EtlExecutionError("ETL recipe not found")

    saved = recipe_response.data[0]
    recipe = normalize_recipe(saved.get("recipe"))
    dataset_key = str(saved.get("dataset_key") or "")
    stable_output_key = (
        str(output_dataset_key or "").strip()
        or build_output_dataset_key(schedule_id or f"recipe:{recipe_id}")
    )
    run_id = create_etl_run(
        client,
        user_id=user_id,
        recipe_id=recipe_id,
        dataset_key=dataset_key,
        output_dataset_key=stable_output_key,
        recipe=recipe,
        trigger_kind=trigger_kind,
        schedule_id=schedule_id,
    )
    started_monotonic = time.monotonic()
    try:
        source_metadata = get_storage_object_metadata(
            settings.AGENT_SESSION_STORAGE_BUCKET,
            f"{user_id}/{dataset_key}",
        )
        handle = load_handle_from_storage(user_id, dataset_key, None)
        if handle is None:
            raise ValueError("Unsupported tabular source")
        mapping = recipe.get("column_mapping") or {}
        contract_readiness = validate_data_contract(
            recipe.get("data_contract"),
            mapping,
            handle.column_names(),
        )
        if (
            (recipe.get("data_contract") or {}).get("enforcement_mode") == "strict"
            and contract_readiness["status"] != "ready"
        ):
            missing = ", ".join(contract_readiness.get("missing") or [])
            raise EtlExecutionError(
                f"Data contract is not ready for strict execution: {missing or 'validation failed'}"
            )
        profile = recipe.get("cleaning_profile") or "standard"
        _notes, handle = handle.prepare_for_analysis(mapping, profile, recipe)
        return publish_transformed_handle(
            client,
            user_id=user_id,
            handle=handle,
            run_id=run_id,
            recipe=recipe,
            dataset_key=dataset_key,
            output_dataset_key=stable_output_key,
            output_name=output_name,
            contract_readiness=contract_readiness,
            source_dataset_key=dataset_key,
            started_monotonic=started_monotonic,
            source_metadata=source_metadata,
        )
    except Exception as exc:
        if run_id:
            (
                client.table("etl_pipeline_runs")
                .update(
                    {
                        "status": "failed",
                        "error_message": str(exc)[:1000],
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                .eq("id", run_id)
                .eq("user_id", user_id)
                .execute()
            )
        raise EtlExecutionError(str(exc)) from exc
