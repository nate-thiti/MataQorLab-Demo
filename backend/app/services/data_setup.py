"""Adaptive, deterministic first-use setup for all supported tabular sources."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

import pandas as pd

from app.core.config import settings
from app.core.json_safety import to_json_safe
from app.core.supabase import get_supabase_client
from app.services.data_cleaning import clean_dataframe
from app.services.dataset_engine import DatasetHandle, TABLE_NAME
from app.services.dataset_loader import load_handle_from_storage
from app.services.domain_analytics import infer_dataset_type, infer_semantic_roles
from app.services.etl_pipeline import (
    build_cleaning_preview,
    normalize_recipe,
    validate_data_contract,
)
from app.services.storage_quota import enforce_customer_storage_quota

SETUP_PROFILES = {"standard", "financial", "conservative", "aggressive"}
SOURCE_TYPES = {"file", "api", "sql", "cloud"}
MAX_SAMPLE_ROWS = 200
MAX_COLUMNS = 200
CRITICAL_ROLES = {
    "sales", "cost", "profit", "gross_amount", "net_amount", "quantity",
    "date", "timestamp", "due_date", "order_id", "invoice_id", "line_id",
    "customer_id", "currency", "tax", "discount",
}


def _safe_text(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _safe_records(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    records: List[Dict[str, Any]] = []
    for raw in rows[:MAX_SAMPLE_ROWS]:
        if not isinstance(raw, dict):
            continue
        records.append({str(key)[:300]: value for key, value in list(raw.items())[:MAX_COLUMNS]})
    return records


def _inferred_type(series: pd.Series) -> tuple[str, float]:
    values = series.dropna()
    if values.empty:
        return "empty", 1.0
    if pd.api.types.is_bool_dtype(values):
        return "boolean", 0.99
    if pd.api.types.is_numeric_dtype(values):
        return "number", 0.98
    if pd.api.types.is_datetime64_any_dtype(values):
        return "date", 0.98
    text = values.astype(str).str.strip()
    numeric = pd.to_numeric(text.str.replace(r"[,$฿€£¥ ]", "", regex=True), errors="coerce")
    numeric_rate = float(numeric.notna().mean())
    if numeric_rate >= 0.9:
        return "number", numeric_rate
    with pd.option_context("mode.chained_assignment", None):
        parsed_dates = pd.to_datetime(text, errors="coerce", format="mixed")
    date_rate = float(parsed_dates.notna().mean())
    if date_rate >= 0.85:
        return "date", date_rate
    distinct_rate = float(values.nunique(dropna=True) / max(len(values), 1))
    if distinct_rate <= 0.35:
        return "category", max(0.6, 1 - distinct_rate)
    return "text", 0.7


def _domain_label(dataset_type: str) -> str:
    labels = {
        "sales_report": "sales",
        "branch_performance": "sales",
        "financial_accounting": "finance",
        "inventory_snapshot": "inventory",
        "warehouse_movement": "inventory",
        "procurement_purchasing": "procurement",
        "human_resources": "hr",
        "production_manufacturing": "manufacturing",
        "marketing_campaign": "marketing",
        "customer_experience": "customer_experience",
    }
    return labels.get(dataset_type, "general")


def _grain_options(mapping: Mapping[str, str]) -> List[Dict[str, Any]]:
    roles = set(mapping.values())
    options: List[tuple[str, str]] = []
    if "line_id" in roles or ("order_id" in roles and "product" in roles):
        options.append(("order_item", "One order or invoice line"))
    if "order_id" in roles or "invoice_id" in roles:
        options.append(("order", "One order or invoice"))
    if "customer_id" in roles or "customer" in roles:
        options.append(("customer", "One customer"))
    if roles & {"stock_in", "stock_out"}:
        options.append(("inventory_movement", "One inventory movement"))
    if "stock_level" in roles:
        options.append(("inventory_snapshot", "One inventory snapshot record"))
    options.append(("source_record", "One source record"))
    result = []
    seen = set()
    for value, label in options:
        if value in seen:
            continue
        seen.add(value)
        result.append({"value": value, "label": label, "recommended": len(result) == 0})
    result.append({"value": "other", "label": "Other", "recommended": False})
    return result


def _business_questions(domain: str, mapping: Mapping[str, str]) -> List[Dict[str, Any]]:
    roles = set(mapping.values())
    questions: List[Dict[str, Any]] = []
    if domain in {"sales", "finance"} or roles & {"sales", "gross_amount", "net_amount"}:
        recommended = "net" if "net_amount" in roles else "gross" if "gross_amount" in roles else "net"
        questions.extend([
            {
                "id": "revenue_basis", "label": "Revenue basis", "required": True,
                "recommended": recommended,
                "options": [
                    {"value": "net", "label": "Net revenue"},
                    {"value": "gross", "label": "Gross revenue"},
                    {"value": "other", "label": "Other"},
                ],
            },
            {
                "id": "cancellation_policy", "label": "Returns and cancellations", "required": True,
                "recommended": "exclude_cancelled_net_returns",
                "options": [
                    {"value": "exclude_cancelled_net_returns", "label": "Exclude cancelled; subtract returns"},
                    {"value": "exclude_all", "label": "Exclude cancelled and returned rows"},
                    {"value": "include_all", "label": "Include every source row"},
                    {"value": "other", "label": "Other"},
                ],
            },
        ])
    if domain == "inventory":
        questions.append({
            "id": "inventory_basis", "label": "Inventory interpretation", "required": True,
            "recommended": "movement" if roles & {"stock_in", "stock_out"} else "snapshot",
            "options": [
                {"value": "movement", "label": "Stock movements"},
                {"value": "snapshot", "label": "Point-in-time stock"},
                {"value": "other", "label": "Other"},
            ],
        })
    questions.extend([
        {
            "id": "currency", "label": "Currency", "required": bool(roles & {"sales", "cost", "price", "gross_amount", "net_amount"}),
            "recommended": "THB",
            "options": [
                {"value": "THB", "label": "THB"}, {"value": "USD", "label": "USD"},
                {"value": "EUR", "label": "EUR"}, {"value": "other", "label": "Other"},
            ],
        },
        {
            "id": "timezone", "label": "Timezone", "required": bool(roles & {"date", "timestamp"}),
            "recommended": "Asia/Bangkok",
            "options": [
                {"value": "Asia/Bangkok", "label": "Asia/Bangkok"},
                {"value": "UTC", "label": "UTC"},
                {"value": "other", "label": "Other"},
            ],
        },
        {
            "id": "fiscal_year_start", "label": "Fiscal year starts", "required": False,
            "recommended": "01",
            "options": [
                {"value": "01", "label": "January"}, {"value": "04", "label": "April"},
                {"value": "07", "label": "July"}, {"value": "10", "label": "October"},
                {"value": "other", "label": "Other"},
            ],
        },
    ])
    return questions


def build_scan_result(
    rows: Any,
    *,
    source_type: str,
    source_label: str,
    row_count: Optional[int] = None,
    row_count_exact: bool = False,
) -> Dict[str, Any]:
    """Return bounded schema intelligence without retaining raw sample rows."""
    records = _safe_records(rows)
    if not records:
        raise ValueError("The source returned no tabular sample rows")
    frame = pd.DataFrame(records)
    frame.columns = [str(column)[:300] for column in frame.columns]
    role_to_column = infer_semantic_roles(frame)
    mapping = {str(column): role for role, column in role_to_column.items()}
    columns: List[Dict[str, Any]] = []
    for column in list(frame.columns)[:MAX_COLUMNS]:
        inferred, type_confidence = _inferred_type(frame[column])
        role = mapping.get(str(column), "")
        normalized = re.sub(r"[^a-z0-9]+", "_", str(column).lower()).strip("_")
        role_confidence = 0.0
        if role:
            role_confidence = 0.96 if normalized == role else 0.86 if role in normalized else 0.76
            if inferred == "date" and role in {"date", "timestamp", "due_date"}:
                role_confidence = max(role_confidence, 0.94)
        null_count = int(frame[column].isna().sum())
        columns.append({
            "name": str(column),
            "inferred_type": inferred,
            "type_confidence": round(type_confidence, 3),
            "null_count": null_count,
            "null_rate": round(null_count / max(len(frame), 1), 4),
            "distinct_sample": int(frame[column].nunique(dropna=True)),
            "suggested_role": role,
            "role_confidence": round(role_confidence, 3),
            "needs_review": not role or role_confidence < 0.85 or role in CRITICAL_ROLES,
            "critical": role in CRITICAL_ROLES,
        })
    dataset_type = infer_dataset_type(role_to_column)
    domain = _domain_label(dataset_type)
    fingerprint_payload = {
        "source_type": source_type,
        "columns": [(item["name"], item["inferred_type"]) for item in columns],
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    count = int(row_count) if row_count is not None else len(frame)
    return to_json_safe({
        "source_type": source_type,
        "source_label": _safe_text(source_label, 300),
        "row_count": count,
        "row_count_exact": bool(row_count_exact),
        "sample_rows": len(frame),
        "column_count": len(columns),
        "columns": columns,
        "suggested_mapping": {item["name"]: item["suggested_role"] for item in columns},
        "suggested_domain": domain,
        "domain_options": [
            {"value": value, "label": label, "recommended": value == domain}
            for value, label in (
                ("sales", "Sales"), ("inventory", "Inventory"), ("finance", "Finance"),
                ("procurement", "Procurement"), ("hr", "Human resources"),
                ("manufacturing", "Manufacturing"), ("marketing", "Marketing"),
                ("customer_experience", "Customer experience"), ("general", "General business data"),
                ("other", "Other"),
            )
        ],
        "grain_options": _grain_options(mapping),
        "primary_id_candidates": [
            item["name"] for item in columns
            if item["suggested_role"] in {"line_id", "order_id", "invoice_id", "customer_id", "document_no"}
        ],
        "date_candidates": [
            item["name"] for item in columns
            if item["suggested_role"] in {"date", "timestamp", "due_date"} or item["inferred_type"] == "date"
        ],
        "business_questions": _business_questions(domain, mapping),
        "source_fingerprint": fingerprint,
    })


def preview_setup_rows(
    rows: Any,
    *,
    mapping: Dict[str, str],
    cleaning_profile: str,
    recipe: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    records = _safe_records(rows)
    if not records:
        raise ValueError("No sample rows are available for cleaning preview")
    profile = cleaning_profile if cleaning_profile in SETUP_PROFILES else "standard"
    before = pd.DataFrame(records)
    normalized = normalize_recipe({
        **(recipe or {}),
        "cleaning_profile": profile,
        "column_mapping": mapping,
    })
    _notes, after = clean_dataframe(before, mapping, profile, normalized)
    report = dict(after.attrs.get("cleaning_report") or {})
    payload = build_cleaning_preview(
        before, after, report, mapping,
        sampled=True,
        total_rows=len(before),
    )
    payload["invalid_date_issues"] = [
        {"column": str(column), "count": int(count), "recommended_action": "flag"}
        for column, count in (report.get("invalid_dates") or {}).items()
        if int(count or 0) > 0
    ]
    # Setup sessions retain issue metadata, never raw preview values. The client
    # already holds its bounded file sample in memory for the current tab.
    payload.pop("before", None)
    payload.pop("after", None)
    if isinstance(payload.get("cleaning_report"), dict):
        payload["cleaning_report"].pop("preview", None)
    payload["contract_readiness"] = validate_data_contract(
        normalized.get("data_contract"), mapping, list(map(str, before.columns))
    )
    return to_json_safe(payload)


def _load_api_handle(user_id: str, connection_id: str, *, sample_only: bool = False) -> DatasetHandle:
    from app.services.connection_secrets import hydrate_api_connection
    from app.services.external_api import fetch_from_connection
    from app.services.json_structure import flatten_json_to_records
    from app.services.large_data_ingest import ingest_api_connection, records_to_handle

    client = get_supabase_client()
    response = client.table("api_connections").select("*").eq(
        "id", connection_id
    ).eq("user_id", user_id).limit(1).execute()
    if not response.data:
        raise ValueError("API connection not found")
    connection = hydrate_api_connection(response.data[0])
    if sample_only:
        records = flatten_json_to_records(fetch_from_connection(connection).json())[:MAX_SAMPLE_ROWS]
        handle = records_to_handle(records)
    else:
        handle = ingest_api_connection(connection)
    if handle is None or handle.row_count() == 0:
        raise ValueError("API returned no tabular rows")
    return handle


def _load_sql_handle(
    user_id: str,
    connection_id: str,
    table_name: str,
    *,
    sample_only: bool = False,
) -> DatasetHandle:
    from app.services.connection_secrets import hydrate_database_connection
    from app.services.sql_execution import (
        build_db_url, build_select_all_query, create_db_engine,
        execute_select_to_handle, is_supported_db_provider,
    )

    client = get_supabase_client()
    response = client.table("database_connections").select("*").eq(
        "id", connection_id
    ).eq("user_id", user_id).limit(1).execute()
    if not response.data:
        raise ValueError("Database connection not found")
    connection = hydrate_database_connection(response.data[0])
    provider = _safe_text(connection.get("provider"), 40).lower()
    if not is_supported_db_provider(provider):
        raise ValueError("Unsupported database provider")
    engine = create_db_engine(build_db_url(
        provider,
        connection.get("username"), connection.get("password_encrypted") or "",
        connection.get("host"), connection.get("port"), connection.get("db_name"),
    ), provider)
    query = build_select_all_query(table_name, MAX_SAMPLE_ROWS if sample_only else None)
    return execute_select_to_handle(engine, query, provider)


def load_setup_handle(
    user_id: str,
    source_type: str,
    source_ref: Mapping[str, Any],
    *,
    sample_only: bool = False,
) -> DatasetHandle:
    if source_type == "file":
        file_name = _safe_text(source_ref.get("file_name"), 500)
        handle = load_handle_from_storage(user_id, file_name, None)
        if handle is None:
            raise ValueError("Unsupported tabular file")
        if sample_only:
            return DatasetHandle.from_dataframe(handle.to_pandas(limit=MAX_SAMPLE_ROWS))
        return handle
    if source_type == "api":
        return _load_api_handle(user_id, _safe_text(source_ref.get("connection_id"), 100), sample_only=sample_only)
    if source_type == "sql":
        return _load_sql_handle(
            user_id,
            _safe_text(source_ref.get("connection_id"), 100),
            _safe_text(source_ref.get("table_name"), 300),
            sample_only=sample_only,
        )
    if source_type == "cloud":
        from app.services.cloud_dataset import load_cloud_handle

        connection_id = _safe_text(source_ref.get("connection_id"), 100)
        client = get_supabase_client()
        response = client.table("cloud_dataset_connections").select("*").eq(
            "id", connection_id
        ).eq("user_id", user_id).limit(1).execute()
        if not response.data:
            raise ValueError("Cloud dataset connection not found")
        handle, _metadata = load_cloud_handle(response.data[0])
        if sample_only:
            return DatasetHandle.from_dataframe(
                handle.to_pandas(limit=MAX_SAMPLE_ROWS)
            )
        return handle
    raise ValueError("Unsupported source type")


def _materialize_source_handle(user_id: str, session_id: str, handle: DatasetHandle) -> str:
    export_handle = DatasetHandle.for_sql_execution(handle)
    path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            path = tmp.name
        escaped = path.replace("'", "''")
        export_handle._con.execute(
            f"COPY (SELECT * FROM {TABLE_NAME}) TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        storage_name = f"data_setup_{session_id}_raw.parquet"
        storage_path = f"{user_id}/{storage_name}"
        enforce_customer_storage_quota(user_id, os.path.getsize(path), storage_path)
        with open(path, "rb") as upload:
            get_supabase_client().storage.from_(settings.AGENT_SESSION_STORAGE_BUCKET).upload(
                path=storage_path,
                file=upload,
                file_options={"content-type": "application/octet-stream", "upsert": "true"},
            )
        return storage_name
    finally:
        if path and os.path.exists(path):
            os.unlink(path)


def process_data_setup_session(session_id: str, user_id: str) -> None:
    """Thin compatibility runner — Workflow Engine owns sequencing decisions.

    Idempotent when session is already ``ready``. Product data-setup execution
    must go through ``WorkflowEngine.run_until_idle`` / ``execute_step`` only.
    """
    from app.services.workflow.engine import WorkflowEngine
    from app.services.workflow.state import update_session_summary

    client = get_supabase_client()
    now = datetime.now(timezone.utc).isoformat()
    try:
        response = client.table("data_setup_sessions").select("*").eq(
            "id", session_id
        ).eq("user_id", user_id).limit(1).execute()
        if not response.data:
            return
        session = response.data[0]
        if session.get("status") == "ready":
            return

        engine = WorkflowEngine(client=client)

        # Do not clobber an in-progress confirmation pause.
        if session.get("status") == "awaiting_answers":
            decision = engine.get_next_action(
                session_id, session=session, user_id=user_id
            )
            if decision.action == "awaiting_user":
                return
            # Resolution happened — continue into the engine loop below.

        client.table("data_setup_sessions").update({
            "status": "processing", "current_step": "processing", "updated_at": now,
            "error_message": None,
            "processing_progress": {"percent": 10, "stage": "workflow_engine"},
        }).eq("id", session_id).eq("user_id", user_id).execute()

        decision = engine.run_until_idle(
            session_id,
            user_id=user_id,
            session=session,
        )
        if decision.action == "awaiting_user":
            client.table("data_setup_sessions").update({
                "status": "awaiting_answers",
                "processing_progress": {
                    "percent": 50,
                    "stage": "awaiting_user",
                    "step": decision.step_type,
                },
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", session_id).eq("user_id", user_id).execute()
            update_session_summary(
                session_id,
                user_id,
                next_action=decision.step_type,
                client=client,
            )
            return
        if decision.action == "blocked":
            raise ValueError(decision.reason or "Workflow blocked")
        if decision.action != "complete":
            raise ValueError(decision.reason or "Workflow did not complete")

        # Finalize owns ready; refresh to confirm.
        refreshed = client.table("data_setup_sessions").select("status").eq(
            "id", session_id
        ).eq("user_id", user_id).limit(1).execute()
        status = ((refreshed.data or [{}])[0]).get("status")
        if status != "ready":
            raise ValueError("Finalize did not mark session ready")
        update_session_summary(
            session_id,
            user_id,
            next_action=None,
            last_failed_step="",
            client=client,
        )
    except Exception as exc:
        client.table("data_setup_sessions").update({
            "status": "failed", "current_step": "processing",
            "error_message": str(exc)[:2000],
            "processing_progress": {"percent": 100, "stage": "failed"},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", session_id).eq("user_id", user_id).execute()
        from app.services.job_dlq import enqueue_dead_letter

        failed_session = locals().get("session") or {}
        try:
            update_session_summary(
                session_id,
                user_id,
                last_failed_step=str(
                    getattr(locals().get("decision"), "step_type", None) or ""
                ) or None,
                client=client,
            )
        except Exception:
            pass
        enqueue_dead_letter(
            client,
            job_kind="data_setup",
            job_key=session_id,
            error_message=str(exc),
            error_code="data_setup_failed",
            user_id=user_id,
            organization_id=failed_session.get("organization_id"),
            workspace_id=failed_session.get("workspace_id"),
            payload={"session_id": session_id},
        )
