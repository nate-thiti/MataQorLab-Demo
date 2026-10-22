"""Owner-scoped Visualization report and chart persistence."""
from __future__ import annotations

import json
import hashlib
import logging
import math
import re
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Mapping

import pandas as pd

from app.core.config import settings
from app.core.supabase import get_supabase_client
from app.services.dataset_engine import DatasetHandle
from app.services.dashboard_intelligence import (
    apply_chart_guardrails,
    build_decision_insights,
    build_dashboard_plan,
    build_grounded_story,
    enrich_semantic_schema,
    judge_dashboard_quality,
    upgrade_dashboard_spec_v4,
)
from app.services.storage_quota import enforce_customer_storage_quota

logger = logging.getLogger("mataqorlab.visualizations")

ALLOWED_CHART_TYPES = {"bar", "line", "area", "pie", "pareto"}
ALLOWED_REPORT_STATUSES = {"draft", "final"}
ALLOWED_CREATED_VIA = {"workspace", "chat", "ai"}
MAX_CHART_ROWS = 500
MAX_CHART_BYTES = 300_000
MAX_REPORTS = 100
MAX_FILTER_OPTIONS = 80
MAX_DASHBOARD_WIDGETS = 12
MAX_DASHBOARD_FILTERS = 8
MAX_DETAIL_ROWS = 200
MAX_DASHBOARD_SPEC_BYTES = 64_000
ALLOWED_WIDGET_SPANS = {4, 6, 8, 12}
ALLOWED_TIME_GRAINS = {"day", "week", "month", "quarter", "year"}
ALLOWED_VALUE_FORMATS = {"auto", "number", "compact", "percent", "currency"}
DASHBOARD_CACHE_TTL_SECONDS = 30
DASHBOARD_CACHE_MAX_ENTRIES = 128
_dashboard_result_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
_dashboard_cache_lock = Lock()


class VisualizationError(ValueError):
    pass


def _text(value: Any, *, maximum: int, fallback: str = "") -> str:
    result = str(value or fallback).strip()
    if len(result) > maximum:
        raise VisualizationError(f"Text exceeds {maximum} characters")
    return result


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def _dashboard_cache_key(
    user_id: str,
    report_id: str,
    source: dict[str, Any],
    spec: dict[str, Any],
    filters: dict[str, Any] | None,
    row_count: int,
    provenance: dict[str, Any] | None = None,
) -> str:
    payload = json.dumps(
        [user_id, report_id, source, spec, filters or {}, row_count, provenance or {}],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _dashboard_cache_get(key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    with _dashboard_cache_lock:
        cached = _dashboard_result_cache.get(key)
        if not cached:
            return None
        created_at, value = cached
        if now - created_at > DASHBOARD_CACHE_TTL_SECONDS:
            _dashboard_result_cache.pop(key, None)
            return None
        _dashboard_result_cache.move_to_end(key)
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _dashboard_cache_set(key: str, value: dict[str, Any]) -> None:
    with _dashboard_cache_lock:
        _dashboard_result_cache[key] = (
            time.monotonic(),
            json.loads(json.dumps(value, ensure_ascii=False, default=str)),
        )
        _dashboard_result_cache.move_to_end(key)
        while len(_dashboard_result_cache) > DASHBOARD_CACHE_MAX_ENTRIES:
            _dashboard_result_cache.popitem(last=False)


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def normalize_chart(chart: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(chart, dict):
        raise VisualizationError("Chart must be an object")
    chart_type = str(chart.get("chart_type") or "").strip().lower()
    if chart_type not in ALLOWED_CHART_TYPES:
        raise VisualizationError("Unsupported chart type")
    config = chart.get("config") or {}
    data = chart.get("data") or []
    if not isinstance(config, dict):
        raise VisualizationError("Chart config must be an object")
    if not isinstance(data, list) or not data:
        raise VisualizationError("Chart data must be a non-empty array")
    if len(data) > MAX_CHART_ROWS:
        raise VisualizationError(f"Chart data is limited to {MAX_CHART_ROWS} rows")
    if any(not isinstance(row, dict) for row in data):
        raise VisualizationError("Every chart row must be an object")
    normalized = {
        "chart_type": chart_type,
        "title": _text(
            chart.get("title") or config.get("title"),
            maximum=160,
            fallback="Untitled chart",
        ),
        "subtitle": _text(chart.get("subtitle"), maximum=1000),
        "config": config,
        "data": data,
        "insight": _text(chart.get("insight"), maximum=10_000),
    }
    if _json_size(normalized) > MAX_CHART_BYTES:
        raise VisualizationError(
            f"Chart snapshot is limited to {MAX_CHART_BYTES // 1000} KB"
        )
    return normalized


def _owned_report(client: Any, user_id: str, report_id: str) -> dict[str, Any]:
    response = (
        client.table("visualization_reports")
        .select("*")
        .eq("id", report_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise VisualizationError("Visualization report not found")
    return response.data[0]


def _persist_decision_packet(
    client: Any,
    user_id: str,
    report_id: str,
    report: dict[str, Any],
    packet: dict[str, Any],
) -> dict[str, Any]:
    from app.services.decision_packet import packet_persist_payload, read_packet_from_report

    payload = packet_persist_payload(report, packet)
    enforce_customer_storage_quota(user_id, _json_size(payload))
    try:
        response = (
            client.table("visualization_reports")
            .update(payload)
            .eq("id", report_id)
            .eq("user_id", user_id)
            .execute()
        )
        if response.data:
            return dict(response.data[0])
    except Exception as exc:
        message = str(exc)
        if "decision_packet" not in message and "PGRST204" not in message:
            raise
    fallback = {
        "dashboard_spec": payload["dashboard_spec"],
        "updated_at": payload["updated_at"],
    }
    response = (
        client.table("visualization_reports")
        .update(fallback)
        .eq("id", report_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        raise VisualizationError("Could not update decision packet")
    updated = dict(response.data[0])
    updated["decision_packet"] = read_packet_from_report({
        **updated,
        "decision_packet": packet,
        "dashboard_spec": fallback["dashboard_spec"],
    })
    return updated


def _attach_decision_packet_to_dashboard(
    report: dict[str, Any],
    response_payload: dict[str, Any],
    *,
    packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.services.decision_packet import (
        enrich_decision_insights,
        evaluate_staleness,
        read_packet_from_report,
        source_fingerprint,
    )

    live_fp = source_fingerprint(response_payload.get("source") or report.get("source_config"))
    state = evaluate_staleness(
        packet if packet is not None else read_packet_from_report(report),
        live_fingerprint=live_fp,
    )
    response_payload["decision_insights"] = enrich_decision_insights(
        response_payload.get("decision_insights") or [],
        state,
    )
    response_payload["decision_packet"] = state
    response_payload["provenance"] = {
        "live_fingerprint": live_fp,
        "proven_fingerprint": state.get("proven_fingerprint"),
        "proven_at": state.get("proven_at"),
        "is_stale": bool(state.get("is_stale")),
        "lifecycle": state.get("lifecycle"),
    }
    return response_payload


def _trusted_source(
    client: Any,
    user_id: str,
    *,
    conversation_id: str | None = None,
    source_message_id: str | None = None,
) -> None:
    if conversation_id:
        conversation = (
            client.table("conversations")
            .select("id")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not conversation.data:
            raise VisualizationError("Conversation does not belong to this user")
    if source_message_id:
        message = (
            client.table("chat_messages")
            .select("id")
            .eq("id", source_message_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not message.data:
            raise VisualizationError("Source message does not belong to this user")


def _infer_source_config(
    client: Any,
    user_id: str,
    conversation_id: str | None,
    source_message_id: str | None = None,
) -> dict[str, Any]:
    if not conversation_id:
        return {}
    try:
        before_created_at = None
        if source_message_id:
            source_message = (
                client.table("chat_messages")
                .select("created_at")
                .eq("id", source_message_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            before_created_at = (
                (source_message.data or [{}])[0].get("created_at")
            )
        query = (
            client.table("chat_messages")
            .select("role,response_metadata,created_at")
            .eq("conversation_id", conversation_id)
            .eq("user_id", user_id)
            .eq("role", "user")
        )
        if before_created_at:
            query = query.lte("created_at", before_created_at)
        response = query.order("created_at", desc=True).limit(30).execute()
    except Exception:
        return {}
    for message in response.data or []:
        metadata = message.get("response_metadata") or {}
        connection = metadata.get("connection") or {}
        if connection.get("id") and connection.get("type") in {"api", "sql"}:
            return {
                "type": connection["type"],
                "connection_id": connection["id"],
                "name": connection.get("name") or "",
                "sql_table": connection.get("sqlTable") or connection.get("sql_table"),
                "column_mapping": metadata.get("column_mapping") or connection.get("mapping") or {},
                "cleaning_profile": metadata.get("cleaning_profile") or "standard",
                "cleaning_recipe": metadata.get("cleaning_recipe") or connection.get("cleaningRecipe") or {},
            }
        if metadata.get("attachment"):
            return {
                "type": "file",
                "file_name": metadata["attachment"],
                "json_path": metadata.get("json_path"),
                "column_mapping": metadata.get("column_mapping") or {},
                "cleaning_profile": metadata.get("cleaning_profile") or "standard",
                "cleaning_recipe": metadata.get("cleaning_recipe") or {},
            }
    return {}


def _normalize_source_config(source: Any) -> dict[str, Any]:
    """Keep only non-secret source identity needed to reload an owned dataset."""
    if not isinstance(source, dict):
        return {}
    source_type = str(source.get("type") or "").strip().lower()
    if source_type == "file" and source.get("file_name"):
        return {
            "type": "file",
            "file_name": _text(source.get("file_name"), maximum=500),
            "json_path": _text(source.get("json_path"), maximum=500) or None,
            "column_mapping": dict(source.get("column_mapping") or {}),
            "cleaning_recipe": dict(source.get("cleaning_recipe") or {}),
            "cleaning_profile": _text(
                source.get("cleaning_profile"), maximum=40, fallback="standard"
            ),
        }
    if source_type in {"api", "sql"} and source.get("connection_id"):
        return {
            "type": source_type,
            "connection_id": _text(source.get("connection_id"), maximum=100),
            "name": _text(source.get("name"), maximum=300),
            "sql_table": (
                _text(source.get("sql_table"), maximum=500)
                if source_type == "sql"
                else None
            ),
            "column_mapping": dict(source.get("column_mapping") or {}),
            "cleaning_recipe": dict(source.get("cleaning_recipe") or {}),
            "cleaning_profile": _text(
                source.get("cleaning_profile"), maximum=40, fallback="standard"
            ),
        }
    if source_type == "cloud" and source.get("connection_id"):
        return {
            "type": "cloud",
            "connection_id": _text(source.get("connection_id"), maximum=100),
            "name": _text(source.get("name"), maximum=300),
            "json_path": _text(source.get("json_path"), maximum=500) or None,
            "column_mapping": dict(source.get("column_mapping") or {}),
            "cleaning_recipe": dict(source.get("cleaning_recipe") or {}),
            "cleaning_profile": _text(source.get("cleaning_profile"), maximum=40, fallback="standard"),
        }
    return {}


def _load_dashboard_handle(
    client: Any,
    user_id: str,
    source: dict[str, Any],
):
    source_type = source.get("type")
    if source_type == "file" and source.get("file_name"):
        from app.services.dataset_loader import load_handle_from_storage

        handle = load_handle_from_storage(
            user_id,
            source["file_name"],
            json_path=source.get("json_path"),
        )
        _, prepared = handle.prepare_for_analysis(
            source.get("column_mapping") or {},
            source.get("cleaning_profile") or "standard",
            source.get("cleaning_recipe") or None,
        )
        return prepared
    if source_type == "api" and source.get("connection_id"):
        from app.services.connection_secrets import hydrate_api_connection
        from app.services.large_data_ingest import ingest_api_connection

        response = (
            client.table("api_connections")
            .select("*")
            .eq("id", source["connection_id"])
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            raise VisualizationError("API connection not found")
        handle = ingest_api_connection(hydrate_api_connection(response.data[0]))
        _, prepared = handle.prepare_for_analysis(
            source.get("column_mapping") or {},
            source.get("cleaning_profile") or "standard",
            source.get("cleaning_recipe") or None,
        )
        return prepared
    if source_type == "sql" and source.get("connection_id") and source.get("sql_table"):
        from app.services.connection_secrets import hydrate_database_connection
        from app.services.sql_execution import (
            build_db_url,
            build_select_all_query,
            create_db_engine,
            execute_select_to_handle,
        )

        response = (
            client.table("database_connections")
            .select("*")
            .eq("id", source["connection_id"])
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            raise VisualizationError("Database connection not found")
        conn = hydrate_database_connection(response.data[0])
        provider = conn.get("provider") or "postgres"
        db_url = build_db_url(
            provider,
            conn.get("username") or "",
            conn.get("password_encrypted") or "",
            conn.get("host") or "",
            int(conn.get("port") or 5432),
            conn.get("db_name") or "",
        )
        engine = create_db_engine(db_url, provider)
        query = build_select_all_query(
            source["sql_table"],
            int(settings.SQL_SYNC_ROW_LIMIT),
        )
        handle = execute_select_to_handle(engine, query, provider)
        _, prepared = handle.prepare_for_analysis(
            source.get("column_mapping") or {},
            source.get("cleaning_profile") or "standard",
            source.get("cleaning_recipe") or None,
        )
        return prepared
    if source_type == "cloud" and source.get("connection_id"):
        from app.services.cloud_dataset import load_cloud_handle

        response = (
            client.table("cloud_dataset_connections").select("*")
            .eq("id", source["connection_id"]).eq("user_id", user_id).limit(1).execute()
        )
        if not response.data:
            raise VisualizationError("Cloud dataset not found")
        handle, _ = load_cloud_handle(response.data[0])
        _, prepared = handle.prepare_for_analysis(
            source.get("column_mapping") or {}, source.get("cleaning_profile") or "standard",
            source.get("cleaning_recipe") or None,
        )
        return prepared
    return None


def _json_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = frame.copy()
    for column in clean.columns:
        if pd.api.types.is_datetime64_any_dtype(clean[column]):
            clean[column] = clean[column].dt.strftime("%Y-%m-%dT%H:%M:%S")
    clean = clean.astype(object).where(pd.notnull(clean), None)
    return json.loads(clean.to_json(orient="records", date_format="iso"))


def _json_safe(value: Any) -> Any:
    """Convert dataframe/DuckDB scalar types into strict JSON primitives."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if hasattr(value, "item") and callable(value.item):
        try:
            value = value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _extract_json_object(text: str) -> dict[str, Any] | None:
    candidate = (text or "").strip()
    candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.I)
    candidate = re.sub(r"\s*```$", "", candidate)
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(candidate[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


def _column_schema(frame: pd.DataFrame) -> list[dict[str, Any]]:
    schema: list[dict[str, Any]] = []
    for name in frame.columns:
        series = frame[name]
        non_null = series.dropna()
        kind = "text"
        if pd.api.types.is_numeric_dtype(series):
            kind = "number"
        elif pd.api.types.is_datetime64_any_dtype(series):
            kind = "date"
        elif not non_null.empty:
            parsed = pd.to_datetime(
                non_null.head(200),
                errors="coerce",
                format="mixed",
            )
            if parsed.notna().mean() >= 0.85:
                kind = "date"
        distinct = int(non_null.nunique()) if not non_null.empty else 0
        options: list[Any] = []
        if kind == "text" and 1 < distinct <= 80:
            options = [str(value) for value in non_null.astype(str).value_counts().head(80).index]
        schema.append(
            {
                "name": str(name),
                "kind": kind,
                "distinct": distinct,
                "options": options[:MAX_FILTER_OPTIONS],
            }
        )
    return schema


def _schema_from_handle(
    handle: DatasetHandle,
    *,
    roles: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Infer dashboard columns from a bounded sample, then compute filter options in DuckDB."""
    sample = handle.to_pandas(limit=min(handle.row_count(), 20_000))
    schema = _column_schema(sample)
    reverse_roles = {
        str(column): str(role)
        for role, column in (roles or {}).items()
        if column
    }
    enriched_text_columns = 0
    for column in schema:
        column["semantic_role"] = reverse_roles.get(column["name"])
        if column["kind"] != "text" or not (1 < column["distinct"] <= 500):
            continue
        if enriched_text_columns >= 12:
            continue
        enriched_text_columns += 1
        qcol = _q(column["name"])
        try:
            result = handle.execute_select(
                f"SELECT CAST({qcol} AS VARCHAR) AS value, COUNT(*) AS frequency "
                f"FROM df WHERE {qcol} IS NOT NULL GROUP BY 1 "
                f"ORDER BY frequency DESC LIMIT {MAX_FILTER_OPTIONS}",
                max_rows=MAX_FILTER_OPTIONS,
            )
            column["options"] = [
                str(value)
                for value in result.get("value", pd.Series(dtype=str)).tolist()
                if value is not None
            ]
            distinct_result = handle.execute_select(
                f"SELECT COUNT(DISTINCT {qcol}) AS value FROM df",
                max_rows=1,
            )
            if not distinct_result.empty:
                column["distinct"] = int(distinct_result.iloc[0]["value"] or 0)
        except Exception:
            pass
    return enrich_semantic_schema(schema, roles, row_count=handle.row_count())


def _ordered_columns(
    schema: list[dict[str, Any]],
    *,
    kind: str,
    preferred_roles: tuple[str, ...],
) -> list[str]:
    candidates = [column for column in schema if column.get("kind") == kind]
    role_order = {role: index for index, role in enumerate(preferred_roles)}
    candidates.sort(
        key=lambda column: (
            role_order.get(str(column.get("semantic_role") or ""), 999),
            int(column.get("distinct") or 0) <= 1,
            str(column.get("name") or ""),
        )
    )
    return [str(column["name"]) for column in candidates]


def _build_dashboard_spec(
    report: dict[str, Any],
    schema: list[dict[str, Any]],
) -> dict[str, Any]:
    return build_dashboard_plan(
        title=report.get("title") or "Adaptive dashboard",
        schema=schema,
        instruction=report.get("analysis_instruction") or report.get("title"),
    )["spec"]


def _normalize_dashboard_spec(
    spec: dict[str, Any] | None,
    schema: list[dict[str, Any]],
    *,
    title: str,
    include_guardrail_metadata: bool = False,
) -> dict[str, Any]:
    """Validate a client-confirmed dashboard spec against the real source schema."""
    fallback = _build_dashboard_spec({"title": title}, schema)
    if not isinstance(spec, dict) or not spec:
        guarded, decisions = apply_chart_guardrails(fallback, schema)
        guarded = upgrade_dashboard_spec_v4(guarded)
        if include_guardrail_metadata:
            guarded["_guardrail_decisions"] = decisions
        return guarded
    if _json_size(spec) > MAX_DASHBOARD_SPEC_BYTES:
        raise VisualizationError("Dashboard specification is too large")
    by_name = {str(column["name"]): column for column in schema}
    filters: list[dict[str, Any]] = []
    for item in list(spec.get("filters") or [])[:MAX_DASHBOARD_FILTERS]:
        field = str((item or {}).get("field") or "")
        if field in by_name:
            filters.append({"field": field, "kind": by_name[field]["kind"]})
    kpis: list[dict[str, Any]] = []
    for item in list(spec.get("kpis") or [])[:6]:
        kind = str((item or {}).get("kind") or "")
        raw_field = (item or {}).get("field")
        field = str(raw_field) if isinstance(raw_field, (str, int, float)) else ""
        if kind == "count":
            kpis.append({
                "kind": "count",
                "field": None,
                "label": _text((item or {}).get("label"), maximum=80, fallback="Rows"),
                "format": (
                    str((item or {}).get("format") or "auto")
                    if str((item or {}).get("format") or "auto") in ALLOWED_VALUE_FORMATS
                    else "auto"
                ),
            })
        elif kind in {"sum", "average"} and field in by_name and by_name[field]["kind"] == "number":
            kpis.append(
                {
                    "kind": kind,
                    "field": field,
                    "label": _text(
                        (item or {}).get("label"),
                        maximum=80,
                        fallback=f"{kind.title()} {field}",
                    ),
                    "format": (
                        str((item or {}).get("format") or "auto")
                        if str((item or {}).get("format") or "auto") in ALLOWED_VALUE_FORMATS
                        else "auto"
                    ),
                    "currency": (
                        str((item or {}).get("currency") or "THB").upper()
                        if re.fullmatch(r"[A-Za-z]{3}", str((item or {}).get("currency") or "THB"))
                        else "THB"
                    ),
                }
            )
    widgets: list[dict[str, Any]] = []
    seen_widget_ids: set[str] = set()
    for index, item in enumerate(
        list(spec.get("widgets") or [])[:MAX_DASHBOARD_WIDGETS]
    ):
        item = item or {}
        kind = str(item.get("kind") or "")
        widget_id = re.sub(r"[^a-zA-Z0-9_-]", "-", str(item.get("id") or f"widget-{index}"))[:80]
        if not widget_id:
            widget_id = f"widget-{index}"
        if widget_id in seen_widget_ids:
            widget_id = f"{widget_id}-{index}"[:80]
        seen_widget_ids.add(widget_id)
        span = (
            int(item.get("span"))
            if str(item.get("span") or "").isdigit()
            else 6
        )
        span = span if span in ALLOWED_WIDGET_SPANS else 6
        if kind == "table":
            columns = [
                str(column)
                for column in list(item.get("columns") or [])
                if str(column) in by_name
            ][:12]
            widgets.append(
                {
                    "id": widget_id,
                    "kind": "table",
                    "title": _text(item.get("title"), maximum=160, fallback="Detail"),
                    "columns": columns or list(by_name)[:10],
                    "span": span if span in {6, 8, 12} else 12,
                    "purpose": "detail",
                }
            )
            continue
        chart_type = str(item.get("chart_type") or "")
        dimension = str(item.get("dimension") or "")
        raw_measure = item.get("measure")
        measure = (
            str(raw_measure)
            if isinstance(raw_measure, (str, int, float))
            else ""
        )
        aggregation = str(item.get("aggregation") or "sum")
        if (
            kind != "chart"
            or chart_type not in ALLOWED_CHART_TYPES
            or dimension not in by_name
            or aggregation not in {"sum", "average", "count"}
            or (
                aggregation != "count"
                and (
                    measure not in by_name
                    or by_name[str(measure)]["kind"] != "number"
                )
            )
        ):
            continue
        requested_limit = (
            int(item.get("limit"))
            if str(item.get("limit") or "").isdigit()
            else 20
        )
        limit = min(12 if chart_type == "pie" else 50, max(5, requested_limit))
        widgets.append(
            {
                "id": widget_id,
                "kind": "chart",
                "chart_type": chart_type,
                "title": _text(item.get("title"), maximum=160, fallback=f"{measure or 'Count'} by {dimension}"),
                "dimension": dimension,
                "measure": measure if aggregation != "count" else None,
                "aggregation": aggregation,
                "time_grain": (
                    (
                        str(item.get("time_grain") or "month")
                        if str(item.get("time_grain") or "month") in ALLOWED_TIME_GRAINS
                        else "month"
                    )
                    if by_name[dimension]["kind"] == "date"
                    else None
                ),
                "limit": limit,
                "span": span,
                "cross_filter": bool(item.get("cross_filter", by_name[dimension]["kind"] != "date")),
                "purpose": (
                    str(item.get("purpose"))
                    if str(item.get("purpose") or "") in {
                        "trend", "ranking", "comparison", "distribution"
                    }
                    else (
                        "trend"
                        if chart_type in {"line", "area"}
                        else "distribution" if chart_type == "pie" else "ranking"
                    )
                ),
                "color": (
                    str(item.get("color")).lower()
                    if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(item.get("color") or ""))
                    else None
                ),
            }
        )
    normalized = {
        "version": 4,
        "title": _text(spec.get("title"), maximum=160, fallback=title),
        "filters": filters,
        "kpis": kpis,
        "widgets": widgets,
        "presentation": spec.get("presentation") if isinstance(spec.get("presentation"), dict) else {},
        "sections": spec.get("sections") if isinstance(spec.get("sections"), list) else [],
        "story": spec.get("story") if isinstance(spec.get("story"), dict) else {},
    }
    guarded, decisions = apply_chart_guardrails(normalized, schema)
    guarded = upgrade_dashboard_spec_v4(guarded)
    if include_guardrail_metadata:
        guarded["_guardrail_decisions"] = decisions
    return guarded


def _bounded_dashboard_spec(
    spec: dict[str, Any] | None,
    *,
    title: str,
) -> dict[str, Any]:
    """Bound an untrusted proposal before persisting; source columns are checked on build."""
    if not isinstance(spec, dict) or not spec:
        return {}
    if _json_size(spec) > MAX_DASHBOARD_SPEC_BYTES:
        raise VisualizationError("Dashboard specification is too large")
    bounded = {
        "version": 4,
        "title": _text(spec.get("title"), maximum=160, fallback=title),
        "filters": [
            item
            for item in list(spec.get("filters") or [])[:MAX_DASHBOARD_FILTERS]
            if isinstance(item, dict)
        ],
        "kpis": [
            item
            for item in list(spec.get("kpis") or [])[:6]
            if isinstance(item, dict)
        ],
        "widgets": [
            item
            for item in list(spec.get("widgets") or [])[:MAX_DASHBOARD_WIDGETS]
            if isinstance(item, dict)
        ],
        "presentation": spec.get("presentation") if isinstance(spec.get("presentation"), dict) else {},
        "sections": [
            item for item in list(spec.get("sections") or [])[:12]
            if isinstance(item, dict)
        ],
        "story": spec.get("story") if isinstance(spec.get("story"), dict) else {},
    }
    return upgrade_dashboard_spec_v4(bounded)


def _dashboard_semantic_warnings(
    spec: dict[str, Any],
    schema: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return actionable, deterministic visualization quality warnings."""
    by_name = {str(column["name"]): column for column in schema}
    warnings: list[dict[str, Any]] = []
    for widget in spec.get("widgets") or []:
        if widget.get("kind") != "chart":
            continue
        widget_id = str(widget.get("id") or "")
        dimension = str(widget.get("dimension") or "")
        measure = str(widget.get("measure") or "")
        chart_type = str(widget.get("chart_type") or "")
        dimension_meta = by_name.get(dimension, {})
        if chart_type == "pie" and int(dimension_meta.get("distinct") or 0) > 12:
            warnings.append({
                "code": "pie_high_cardinality",
                "severity": "warning",
                "widget_id": widget_id,
                "message": "Pie charts are hard to compare when the source has more than 12 categories.",
                "message_th": "Pie chart เปรียบเทียบยากเมื่อข้อมูลต้นทางมีมากกว่า 12 กลุ่ม",
                "suggestion": "Use a bar chart or keep only the most important categories.",
                "suggestion_th": "เปลี่ยนเป็นกราฟแท่งหรือแสดงเฉพาะกลุ่มสำคัญ",
            })
        if chart_type in {"line", "area"} and dimension_meta.get("kind") != "date":
            warnings.append({
                "code": "non_temporal_trend",
                "severity": "warning",
                "widget_id": widget_id,
                "message": "Line and area charts usually need a date or ordered dimension.",
                "message_th": "กราฟเส้นและกราฟพื้นที่ควรใช้วันที่หรือ Dimension ที่มีลำดับ",
                "suggestion": "Use a date field or switch to a bar chart.",
                "suggestion_th": "เลือก Field วันที่หรือเปลี่ยนเป็นกราฟแท่ง",
            })
        if (
            widget.get("aggregation") in {"sum", "average"}
            and re.search(r"(^|[_\s-])(id|code|รหัส|เลขที่)($|[_\s-])", measure, re.I)
        ):
            warnings.append({
                "code": "identifier_aggregation",
                "severity": "error",
                "widget_id": widget_id,
                "message": f"{widget.get('aggregation', '').upper()} on “{measure}” may aggregate an identifier.",
                "message_th": f"{str(widget.get('aggregation') or '').upper()} ที่ “{measure}” อาจเป็นการรวมรหัส",
                "suggestion": "Use COUNT DISTINCT for identifiers or select a business measure.",
                "suggestion_th": "ควรใช้ COUNT DISTINCT สำหรับรหัส หรือเลือก Measure ทางธุรกิจ",
            })
        if (
            chart_type in {"bar", "pareto"}
            and int(dimension_meta.get("distinct") or 0) > 50
            and int(widget.get("limit") or 20) > 30
        ):
            warnings.append({
                "code": "dense_category_axis",
                "severity": "warning",
                "widget_id": widget_id,
                "message": "This category axis may be too dense to read.",
                "message_th": "แกนหมวดหมู่นี้อาจมีข้อมูลแน่นเกินไปจนอ่านยาก",
                "suggestion": "Reduce Top N to 20–30 or add a filter.",
                "suggestion_th": "ลด Top N เหลือ 20–30 หรือเพิ่มตัวกรอง",
            })
    for index, kpi in enumerate(spec.get("kpis") or []):
        if kpi.get("format") == "percent":
            warnings.append({
                "code": "percent_scale_check",
                "severity": "info",
                "widget_id": f"kpi-{index}",
                "message": "Percent formatting expects a ratio where 1 equals 100%.",
                "message_th": "รูปแบบ Percent คาดว่าค่า 1 เท่ากับ 100%",
                "suggestion": "Verify the source is a ratio, not an already-multiplied percentage.",
                "suggestion_th": "ตรวจว่าค่าต้นทางเป็นอัตราส่วน ไม่ใช่เปอร์เซ็นต์ที่คูณ 100 แล้ว",
            })
    return warnings[:20]


def build_visualization_proposal(
    handle: DatasetHandle,
    *,
    title: str,
    roles: dict[str, str] | None = None,
    source_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    schema = _schema_from_handle(handle, roles=roles)
    intelligence = build_dashboard_plan(
        title=title,
        schema=schema,
        instruction=title,
    )
    spec = intelligence["spec"]
    return {
        "action": "propose_visualization",
        "title": spec["title"],
        "question": "เลือกกราฟและตัวกรองที่ต้องการ แล้วกดยืนยันเพื่อสร้าง Visualization",
        "row_count": handle.row_count(),
        "filters": spec["filters"],
        "kpis": spec["kpis"],
        "widgets": spec["widgets"],
        "spec": spec,
        "analysis_intent": intelligence["intent"],
        "dashboard_planning": {
            "selected_composition": intelligence["selected_composition"],
            "selected_score": intelligence["selected_score"],
            "widget_candidates_evaluated": intelligence["widget_candidates_evaluated"],
        },
        "source_config": _normalize_source_config(source_config),
    }


def _where_clause(
    filters: dict[str, Any] | None,
    spec: dict[str, Any],
) -> str:
    allowed = {
        str(item.get("field")): str(item.get("kind"))
        for item in spec.get("filters") or []
    }
    allowed.update({
        str(item.get("dimension")): "text"
        for item in spec.get("widgets") or []
        if item.get("kind") == "chart"
        and item.get("cross_filter")
        and not item.get("time_grain")
    })
    clauses: list[str] = []
    for field, value in (filters or {}).items():
        if field not in allowed or value in (None, "", {}):
            continue
        qfield = _q(field)
        if allowed[field] == "date" and isinstance(value, dict):
            start = value.get("from")
            end = value.get("to")
            if start:
                clauses.append(
                    f"TRY_CAST({qfield} AS TIMESTAMP) >= TRY_CAST({_sql_literal(start)} AS TIMESTAMP)"
                )
            if end:
                clauses.append(
                    f"TRY_CAST({qfield} AS TIMESTAMP) < TRY_CAST({_sql_literal(end)} AS TIMESTAMP) + INTERVAL 1 DAY"
                )
        else:
            # Filter choices are serialized through HTML/JSON as strings.  Keep
            # the comparison aligned with the trimmed values exposed by the
            # schema query so harmless source whitespace cannot turn a valid
            # option into an empty dashboard.
            clauses.append(
                f"TRIM(CAST({qfield} AS VARCHAR)) = "
                f"TRIM(CAST({_sql_literal(value)} AS VARCHAR))"
            )
    return (" WHERE " + " AND ".join(clauses)) if clauses else ""


def _dashboard_data(
    handle: DatasetHandle,
    spec: dict[str, Any],
    *,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    where = _where_clause(filters, spec)
    count_result = handle.execute_select(
        f"SELECT COUNT(*) AS value FROM df{where}",
        max_rows=1,
    )
    filtered_row_count = (
        int(count_result.iloc[0]["value"] or 0)
        if not count_result.empty
        else 0
    )
    kpi_selects: list[str] = []
    for index, kpi in enumerate(spec.get("kpis") or []):
        alias = _q(f"kpi_{index}")
        if kpi["kind"] == "count":
            kpi_selects.append(f"COUNT(*) AS {alias}")
        else:
            qfield = _q(kpi["field"])
            function = "AVG" if kpi["kind"] == "average" else "SUM"
            kpi_selects.append(
                f"{function}(TRY_CAST({qfield} AS DOUBLE)) AS {alias}"
            )
    kpi_values: list[dict[str, Any]] = []
    if kpi_selects:
        result = handle.execute_select(
            f"SELECT {', '.join(kpi_selects)} FROM df{where}",
            max_rows=1,
        )
        row = result.iloc[0] if not result.empty else {}
        for index, kpi in enumerate(spec.get("kpis") or []):
            value = row.get(f"kpi_{index}", 0) if hasattr(row, "get") else 0
            kpi_values.append({**kpi, "value": None if pd.isna(value) else value})

    widget_results: list[dict[str, Any]] = []
    for widget in spec.get("widgets") or []:
        if widget["kind"] == "table":
            columns = widget.get("columns") or []
            select_columns = ", ".join(_q(column) for column in columns)
            frame = handle.execute_select(
                f"SELECT {select_columns} FROM df{where} LIMIT {MAX_DETAIL_ROWS}",
                max_rows=MAX_DETAIL_ROWS,
            )
            widget_results.append({**widget, "data": _json_rows(frame)})
            continue
        dimension = widget["dimension"]
        qdimension = _q(dimension)
        limit = int(widget.get("limit") or 20)
        if widget.get("time_grain"):
            dimension_expr = (
                f"DATE_TRUNC('{widget['time_grain']}', "
                f"TRY_CAST({qdimension} AS TIMESTAMP))"
            )
        else:
            dimension_expr = f"CAST({qdimension} AS VARCHAR)"
        if widget["aggregation"] == "count":
            measure_expr = "COUNT(*)"
        else:
            qmeasure = _q(widget["measure"])
            function = "AVG" if widget["aggregation"] == "average" else "SUM"
            measure_expr = f"{function}(TRY_CAST({qmeasure} AS DOUBLE))"
        order = "name" if widget.get("time_grain") else "value DESC"
        null_clause = (
            f" AND {dimension_expr} IS NOT NULL"
            if where
            else f" WHERE {dimension_expr} IS NOT NULL"
        )
        frame = handle.execute_select(
            f"SELECT {dimension_expr} AS name, {measure_expr} AS value "
            f"FROM df{where}{null_clause} "
            f"GROUP BY 1 ORDER BY {order} LIMIT {limit}",
            max_rows=limit,
        )
        widget_results.append({**widget, "data": _json_rows(frame)})
    return _json_safe({
        "kpis": kpi_values,
        "widgets": widget_results,
        "applied_filters": filters or {},
        "filtered_row_count": filtered_row_count,
    })


def generate_dashboard(
    user_id: str,
    report_id: str,
    *,
    force: bool = False,
    filters: dict[str, Any] | None = None,
    dashboard_spec: dict[str, Any] | None = None,
    persist: bool = True,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    report = _owned_report(client, user_id, report_id)
    source_was_missing = not bool(report.get("source_config"))
    source = (
        report.get("source_config")
        or _infer_source_config(client, user_id, report.get("conversation_id"))
        or {}
    )
    source = dict(source)
    source_file = str(source.get("file_name") or "").strip()
    if source_file and not source.get("dataset_version_id"):
        try:
            version_response = (
                client.table("dataset_versions")
                .select(
                    "id,source_fingerprint,recipe_hash,contract_hash,"
                    "output_dataset_key,output_file"
                )
                .eq("user_id", user_id)
                .eq("output_file", source_file)
                .eq("status", "ready")
                .order("version_number", desc=True)
                .limit(1)
                .execute()
            )
            if isinstance(version_response.data, list) and version_response.data:
                version = version_response.data[0]
                source.update({
                    "dataset_version_id": version.get("id"),
                    "source_fingerprint": version.get("source_fingerprint"),
                    "recipe_hash": version.get("recipe_hash"),
                    "contract_hash": version.get("contract_hash"),
                    "output_dataset_key": version.get("output_dataset_key"),
                    "cleaning_recipe": {
                        **(source.get("cleaning_recipe") or {}),
                        "materialized_prepared": True,
                        "dataset_version_id": version.get("id"),
                        "source_fingerprint": version.get("source_fingerprint"),
                        "recipe_hash": version.get("recipe_hash"),
                        "contract_hash": version.get("contract_hash"),
                    },
                })
        except Exception as exc:
            if not any(code in str(exc) for code in ("PGRST205", "42P01")):
                raise
    source_recipe = source.get("cleaning_recipe") or {}
    immutable_version = (
        source.get("dataset_version_id")
        or source_recipe.get("dataset_version_id")
    )
    immutable_fingerprint = (
        source.get("source_fingerprint")
        or source_recipe.get("source_fingerprint")
    )
    response_cache_key = None
    if immutable_version or immutable_fingerprint:
        response_cache_key = "response:" + _dashboard_cache_key(
            user_id,
            report_id,
            source,
            dashboard_spec or report.get("dashboard_spec") or {},
            filters,
            0,
            {
                "dataset_version_id": immutable_version,
                "source_fingerprint": immutable_fingerprint,
                "contract_hash": (
                    source.get("contract_hash")
                    or source_recipe.get("contract_hash")
                ),
                "recipe_hash": (
                    source.get("recipe_hash")
                    or source_recipe.get("recipe_hash")
                ),
            },
        )
        if not force:
            cached_response = _dashboard_cache_get(response_cache_key)
            if cached_response is not None:
                cached_response["cache_hit"] = True
                return cached_response
    try:
        handle = _load_dashboard_handle(client, user_id, source)
    except Exception as exc:
        raise VisualizationError(
            "Could not reload the dashboard data source. Reattach or reconnect the source."
        ) from exc
    total_rows = handle.row_count() if handle is not None else 0
    if handle is None or total_rows == 0:
        charts_response = (
            client.table("visualization_charts")
            .select("data")
            .eq("report_id", report_id)
            .eq("user_id", user_id)
            .order("sort_order")
            .execute()
        )
        fallback_rows: list[dict[str, Any]] = []
        for chart in charts_response.data or []:
            fallback_rows.extend(chart.get("data") or [])
        handle = DatasetHandle.from_dataframe(pd.DataFrame(fallback_rows))
        total_rows = handle.row_count()
    if handle is None or total_rows == 0:
        raise VisualizationError(
            "Dashboard data source is unavailable or returned no rows; the saved layout was not changed."
        )
    semantic_roles = (
        handle.infer_roles_from_sample(
            getattr(handle, "_effective_mapping", None)
            or source.get("column_mapping")
            or {}
        )
        if handle is not None and total_rows
        else {}
    )
    schema = (
        _schema_from_handle(handle, roles=semantic_roles)
        if handle is not None and total_rows
        else []
    )
    intelligence = build_dashboard_plan(
        title=report.get("title") or "Adaptive dashboard",
        schema=schema,
        instruction=report.get("title"),
    )
    saved_spec = report.get("dashboard_spec") or {}
    saved_spec_is_empty = not any(
        saved_spec.get(key) for key in ("filters", "kpis", "widgets")
    )
    requested_spec = (
        dashboard_spec
        if isinstance(dashboard_spec, dict) and dashboard_spec
        else (
            _build_dashboard_spec(report, schema)
            if force or (source_was_missing and saved_spec_is_empty)
            else saved_spec
        )
    ) or _build_dashboard_spec(report, schema)
    spec = _normalize_dashboard_spec(
        requested_spec,
        schema,
        title=report.get("title") or "Adaptive dashboard",
        include_guardrail_metadata=True,
    )
    guardrail_decisions = list(spec.pop("_guardrail_decisions", []))
    semantic_warnings = _dashboard_semantic_warnings(spec, schema)
    if persist:
        update_payload = {
            "source_config": source,
            "dashboard_spec": spec,
            "filter_state": filters or {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if saved_spec and saved_spec != spec:
            _save_dashboard_revision(
                client,
                user_id,
                report_id,
                saved_spec,
                change_summary="Dashboard updated",
            )
        enforce_customer_storage_quota(user_id, _json_size(update_payload))
        (
            client.table("visualization_reports")
            .update(update_payload)
            .eq("id", report_id)
            .eq("user_id", user_id)
            .execute()
        )
    cache_key = _dashboard_cache_key(
        user_id,
        report_id,
        source,
        spec,
        filters,
        total_rows,
        {
            "dataset_version_id": getattr(handle, "_dataset_version_id", None),
            "source_fingerprint": getattr(handle, "_source_fingerprint", None),
            "contract_hash": getattr(handle, "_contract_hash", None),
            "recipe_hash": getattr(handle, "_recipe_hash", None),
        },
    )
    cache_allowed = source.get("type") == "file"
    computed = None if force or not cache_allowed else _dashboard_cache_get(cache_key)
    cache_hit = computed is not None
    if computed is None:
        computed = (
            _dashboard_data(handle, spec, filters=filters)
            if handle is not None and total_rows
            else {"kpis": [], "widgets": [], "applied_filters": filters or {}}
        )
        if cache_allowed:
            _dashboard_cache_set(cache_key, computed)
    decision_insights = build_decision_insights(computed, spec)
    grounded_story = build_grounded_story(
        title=report.get("title") or "Adaptive dashboard",
        computed=computed,
        spec=spec,
        insights=decision_insights,
        context={
            "source": source,
            "source_row_count": total_rows,
            "aggregation_scope": "full_dataset",
            "semantic_warning_count": len(semantic_warnings),
        },
    )
    response_payload = _json_safe({
        "report_id": report_id,
        "source": source,
        "row_count": total_rows,
        "sampled": False,
        "aggregation_scope": "full_dataset",
        "cache_hit": cache_hit,
        "semantic_warnings": semantic_warnings,
        "chart_guardrails": guardrail_decisions,
        "decision_insights": decision_insights,
        "story": grounded_story,
        "analysis_intent": intelligence["intent"],
        "dashboard_planning": {
            "selected_composition": intelligence["selected_composition"],
            "selected_score": intelligence["selected_score"],
            "composition_candidates": intelligence["composition_candidates"],
            "design_candidates": intelligence["design_candidates"],
            "widget_candidates_evaluated": intelligence["widget_candidates_evaluated"],
            "active_spec_score": judge_dashboard_quality(spec, schema, intelligence["intent"]),
        },
        "schema": schema,
        "spec": spec,
        **computed,
    })
    response_payload = _attach_decision_packet_to_dashboard(report, response_payload)
    if persist and response_payload.get("provenance", {}).get("is_stale"):
        from app.services.decision_packet import read_packet_from_report

        stale_packet = response_payload.get("decision_packet") or read_packet_from_report(report)
        try:
            _persist_decision_packet(client, user_id, report_id, report, stale_packet)
        except Exception as exc:
            logger.warning("decision_packet_stale_persist_failed", exc_info=exc)
    if response_cache_key:
        _dashboard_cache_set(response_cache_key, response_payload)
    return response_payload


def _save_dashboard_revision(
    client: Any,
    user_id: str,
    report_id: str,
    dashboard_spec: dict[str, Any],
    *,
    change_summary: str,
) -> None:
    if not dashboard_spec:
        return
    payload = {
        "report_id": report_id,
        "user_id": user_id,
        "dashboard_spec": dashboard_spec,
        "change_summary": _text(change_summary, maximum=500),
    }
    enforce_customer_storage_quota(user_id, _json_size(payload))
    try:
        client.table("visualization_dashboard_revisions").insert(payload).execute()
        old = (
            client.table("visualization_dashboard_revisions")
            .select("id")
            .eq("report_id", report_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .range(30, 80)
            .execute()
        )
        old_ids = [row["id"] for row in (old.data or []) if row.get("id")]
        if old_ids:
            (
                client.table("visualization_dashboard_revisions")
                .delete()
                .eq("user_id", user_id)
                .in_("id", old_ids)
                .execute()
            )
    except Exception as exc:
        logger.warning(
            "visualization_revision_storage_unavailable",
            extra={"report_id": report_id, "error_code": "persistence_failed", "error": str(exc)},
        )


def list_dashboard_revisions(
    user_id: str,
    report_id: str,
    *,
    client: Any | None = None,
) -> list[dict[str, Any]]:
    client = client or get_supabase_client()
    _owned_report(client, user_id, report_id)
    response = (
        client.table("visualization_dashboard_revisions")
        .select("id,change_summary,created_at")
        .eq("report_id", report_id)
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(30)
        .execute()
    )
    return [dict(row) for row in (response.data or [])]


def restore_dashboard_revision(
    user_id: str,
    report_id: str,
    revision_id: str,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    _owned_report(client, user_id, report_id)
    response = (
        client.table("visualization_dashboard_revisions")
        .select("dashboard_spec")
        .eq("id", revision_id)
        .eq("report_id", report_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise VisualizationError("Dashboard revision not found")
    return generate_dashboard(
        user_id,
        report_id,
        dashboard_spec=response.data[0].get("dashboard_spec") or {},
        persist=True,
        client=client,
    )


def create_report_share(
    user_id: str,
    report_id: str,
    *,
    expires_in_days: int = 30,
    allow_detail_rows: bool = False,
    max_views: int | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    _owned_report(client, user_id, report_id)
    days = min(365, max(1, int(expires_in_days or 30)))
    expires_at = datetime.now(timezone.utc) + pd.Timedelta(days=days)
    payload = {
        "report_id": report_id,
        "user_id": user_id,
        "allow_detail_rows": bool(allow_detail_rows),
        "expires_at": expires_at.isoformat(),
        "max_views": (
            min(1_000_000, max(1, int(max_views))) if max_views is not None else None
        ),
    }
    enforce_customer_storage_quota(user_id, _json_size(payload))
    response = client.table("visualization_report_shares").insert(payload).execute()
    if not response.data:
        raise VisualizationError("Could not create share link")
    return dict(response.data[0])


def list_report_shares(
    user_id: str,
    report_id: str,
    *,
    client: Any | None = None,
) -> list[dict[str, Any]]:
    client = client or get_supabase_client()
    _owned_report(client, user_id, report_id)
    response = (
        client.table("visualization_report_shares")
        .select("id,token,allow_detail_rows,expires_at,revoked_at,created_at,max_views,access_count,last_accessed_at")
        .eq("report_id", report_id)
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(30)
        .execute()
    )
    return [dict(row) for row in (response.data or [])]


def revoke_report_share(
    user_id: str,
    report_id: str,
    share_id: str,
    *,
    client: Any | None = None,
) -> None:
    client = client or get_supabase_client()
    _owned_report(client, user_id, report_id)
    response = (
        client.table("visualization_report_shares")
        .update({"revoked_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", share_id)
        .eq("report_id", report_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        raise VisualizationError("Share link not found")


def _sanitize_shared_dashboard_payload(
    dashboard: dict[str, Any],
    *,
    allow_detail_rows: bool,
) -> dict[str, Any]:
    """Remove private V4 source/detail evidence before returning a public share."""
    sanitized = json.loads(json.dumps(dashboard, ensure_ascii=False, default=str))
    sanitized["source"] = {}
    story = sanitized.get("story") or {}
    for evidence in story.get("evidence") or []:
        if evidence.get("kind") == "query_context":
            evidence["source"] = {}
    sanitized["schema"] = [
        {key: value for key, value in column.items() if key != "options"}
        for column in sanitized.get("schema") or []
    ]
    if allow_detail_rows:
        return sanitized
    spec = sanitized.get("spec") or {}
    detail_widget_ids = {
        str(widget.get("id"))
        for widget in spec.get("widgets") or []
        if widget.get("kind") == "table"
    }
    sanitized["widgets"] = [
        widget for widget in sanitized.get("widgets") or []
        if widget.get("kind") != "table"
    ]
    spec["widgets"] = [
        widget for widget in spec.get("widgets") or []
        if widget.get("kind") != "table"
    ]
    story["evidence"] = [
        evidence
        for evidence in story.get("evidence") or []
        if not (
            evidence.get("widget_id") in detail_widget_ids
            or evidence.get("source_widget_id") in detail_widget_ids
        )
    ]
    allowed_evidence_ids = {str(item.get("id")) for item in story.get("evidence") or []}
    story["evidence_ids"] = [
        evidence_id for evidence_id in story.get("evidence_ids") or []
        if evidence_id in allowed_evidence_ids
    ]
    for chapter in story.get("chapters") or []:
        chapter["evidence_ids"] = [
            evidence_id for evidence_id in chapter.get("evidence_ids") or []
            if evidence_id in allowed_evidence_ids
        ]
    sanitized["spec"] = upgrade_dashboard_spec_v4(spec)
    return sanitized


def get_shared_dashboard(
    token: str,
    *,
    filters: dict[str, Any] | None = None,
    count_view: bool = True,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    try:
        normalized_token = str(uuid.UUID(str(token)))
    except ValueError as exc:
        raise VisualizationError("Share link not found") from exc
    response = (
        client.table("visualization_report_shares")
        .select("id,report_id,user_id,allow_detail_rows,expires_at,revoked_at,max_views,access_count,last_accessed_at")
        .eq("token", normalized_token)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise VisualizationError("Share link not found")
    share = response.data[0]
    expires_at = pd.to_datetime(share.get("expires_at"), utc=True, errors="coerce")
    if (
        share.get("revoked_at")
        or pd.isna(expires_at)
        or expires_at.to_pydatetime() <= datetime.now(timezone.utc)
    ):
        raise VisualizationError("Share link has expired or was revoked")
    access_count = int(share.get("access_count") or 0)
    max_views = share.get("max_views")
    if count_view and max_views is not None and access_count >= int(max_views):
        raise VisualizationError("Share link view limit has been reached")
    effective_access_count = access_count
    if count_view:
        access_update = (
            client.table("visualization_report_shares")
            .update({
                "access_count": access_count + 1,
                "last_accessed_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("id", share["id"])
            .eq("access_count", access_count)
            .execute()
        )
        if not access_update.data:
            raise VisualizationError("Share link is busy; retry the request")
        effective_access_count += 1
    report = _owned_report(client, str(share["user_id"]), str(share["report_id"]))
    dashboard = generate_dashboard(
        str(share["user_id"]),
        str(share["report_id"]),
        filters=filters,
        persist=False,
        client=client,
    )
    dashboard = _sanitize_shared_dashboard_payload(
        dashboard,
        allow_detail_rows=bool(share.get("allow_detail_rows")),
    )
    from app.services.decision_packet import decision_brief

    brief = decision_brief(report, dashboard)
    return {
        "report": {
            "id": report.get("id"),
            "title": report.get("title"),
            "description": report.get("description"),
            "executive_summary": report.get("executive_summary"),
            "updated_at": report.get("updated_at"),
            "status": report.get("status"),
            "decision_packet": brief,
        },
        "dashboard": dashboard,
        "decision_brief": brief,
        "share": {
            "expires_at": share.get("expires_at"),
            "allow_detail_rows": bool(share.get("allow_detail_rows")),
            "max_views": max_views,
            "access_count": effective_access_count,
        },
    }


def create_dashboard_template(
    user_id: str,
    report_id: str,
    *,
    name: str,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    report = _owned_report(client, user_id, report_id)
    spec = report.get("dashboard_spec") or {}
    if not spec:
        raise VisualizationError("Save the dashboard before creating a template")
    payload = {
        "user_id": user_id,
        "name": _text(name, maximum=160, fallback=report.get("title") or "Template"),
        "dashboard_spec": spec,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    enforce_customer_storage_quota(user_id, _json_size(payload))
    response = client.table("visualization_dashboard_templates").insert(payload).execute()
    if not response.data:
        raise VisualizationError("Could not create dashboard template")
    return dict(response.data[0])


def list_dashboard_templates(
    user_id: str,
    *,
    client: Any | None = None,
) -> list[dict[str, Any]]:
    client = client or get_supabase_client()
    response = (
        client.table("visualization_dashboard_templates")
        .select("id,name,created_at,updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(50)
        .execute()
    )
    return [dict(row) for row in (response.data or [])]


def preview_dashboard_template(
    user_id: str,
    report_id: str,
    template_id: str,
    *,
    persist: bool = False,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    _owned_report(client, user_id, report_id)
    response = (
        client.table("visualization_dashboard_templates")
        .select("dashboard_spec")
        .eq("id", template_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise VisualizationError("Dashboard template not found")
    return generate_dashboard(
        user_id,
        report_id,
        dashboard_spec=response.data[0].get("dashboard_spec") or {},
        persist=persist,
        client=client,
    )


def delete_dashboard_template(
    user_id: str,
    template_id: str,
    *,
    client: Any | None = None,
) -> None:
    client = client or get_supabase_client()
    response = (
        client.table("visualization_dashboard_templates")
        .delete()
        .eq("id", template_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        raise VisualizationError("Dashboard template not found")


def _resolve_planner_spec(
    parsed: dict[str, Any] | None,
    base_spec: dict[str, Any],
    schema: list[dict[str, Any]],
    *,
    title: str,
    include_guardrail_metadata: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    """Validate an AI proposal or return the already-valid deterministic spec."""
    proposed = parsed.get("spec") if isinstance(parsed, dict) else None
    if not isinstance(proposed, dict):
        return base_spec, {}, "invalid_ai_plan"
    try:
        normalized = _normalize_dashboard_spec(
            proposed,
            schema,
            title=title,
            include_guardrail_metadata=include_guardrail_metadata,
        )
    except VisualizationError:
        return base_spec, {}, "invalid_ai_plan"
    rationale = (
        parsed.get("rationale")
        if isinstance(parsed.get("rationale"), dict)
        else {}
    )
    return normalized, rationale, None


async def plan_dashboard(
    user_id: str,
    report_id: str,
    *,
    instruction: str,
    current_spec: dict[str, Any] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Ask the LLM for a schema-only dashboard plan, then validate and compute it."""
    from app.services.chat.llm_client import LlmClient
    from app.services.quota_service import get_user_tier, record_token_usage

    client = client or get_supabase_client()
    report = _owned_report(client, user_id, report_id)
    source = report.get("source_config") or _infer_source_config(
        client, user_id, report.get("conversation_id")
    )
    handle = _load_dashboard_handle(client, user_id, source)
    if handle is None or handle.row_count() == 0:
        raise VisualizationError("The dashboard source has no rows to plan")
    semantic_roles = handle.infer_roles_from_sample(
        getattr(handle, "_effective_mapping", None)
        or source.get("column_mapping")
        or {}
    )
    schema = _schema_from_handle(handle, roles=semantic_roles)
    request_text = _text(
        instruction,
        maximum=1000,
        fallback="Improve this dashboard for decision making",
    )
    deterministic_plan = build_dashboard_plan(
        title=report.get("title") or "Adaptive dashboard",
        schema=schema,
        instruction=request_text,
    )
    safe_schema = [
        {
            "name": column.get("name"),
            "kind": column.get("kind"),
            "distinct": column.get("distinct"),
            "semantic_role": column.get("semantic_role"),
            "semantic_type": column.get("semantic_type"),
            "recommended_aggregation": column.get("recommended_aggregation"),
        }
        for column in schema[:80]
    ]
    base_spec = _normalize_dashboard_spec(
        current_spec or report.get("dashboard_spec") or deterministic_plan["spec"],
        schema,
        title=report.get("title") or "Adaptive dashboard",
    )
    prompt = (
        "You are a dashboard planner. Return one JSON object only with keys `spec` and "
        "`rationale`. Never return SQL, HTML, React, markdown, or raw data. Build a concise "
        "decision dashboard using only fields in SCHEMA. `spec` must use Dashboard DSL version 4 "
        "with flat `widgets` plus `presentation`, `sections`, and an evidence-grounded `story` "
        "blueprint. Sections may only reference widget ids from the same spec. Never invent narrative "
        "facts or numbers; runtime storytelling is built from verified evidence. Allowed widget kinds: chart, table. "
        "Allowed chart types: bar, line, area, pie, pareto. Allowed aggregations: sum, average, count. "
        "Use dates for line/area trends; do not sum identifiers; pie charts must use Top N <= 12; "
        "use spans 4, 6, 8, or 12; at most 6 KPIs and 12 widgets. `rationale` must be an object "
        "mapping widget ids to one short reason. Preserve useful current widgets unless the user "
        "asks to replace them. Treat ANALYSIS_INTENT as the required decision coverage and improve "
        "on the deterministic candidate without reducing semantic safety.\n"
        f"USER_REQUEST={json.dumps(request_text, ensure_ascii=False)}\n"
        f"ANALYSIS_INTENT={json.dumps(deterministic_plan['intent'], ensure_ascii=False)}\n"
        f"SCHEMA={json.dumps(safe_schema, ensure_ascii=False)}\n"
        f"DETERMINISTIC_CANDIDATE={json.dumps(deterministic_plan['spec'], ensure_ascii=False)}\n"
        f"CURRENT_SPEC={json.dumps(base_spec, ensure_ascii=False)}"
    )
    tier = get_user_tier(user_id).value
    model = (
        settings.LLM_MODEL_PREMIUM
        if tier in {"plus", "pro"}
        else settings.LLM_MODEL_FREE
    )
    llm = LlmClient()
    parsed: dict[str, Any] | None = None
    fallback_reason: str | None = None
    response = None
    try:
        response = await llm.safe_chat_completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2200,
        )
    except Exception as exc:
        fallback_reason = "planner_unavailable"
        logger.warning(
            "dashboard_planner_fallback",
            extra={"report_id": report_id, "error_code": "dependency_unavailable", "error": str(exc)},
        )
    if response is not None:
        try:
            await record_token_usage(
                user_id,
                getattr(getattr(response, "usage", None), "total_tokens", None),
            )
        except Exception as exc:
            logger.warning(
                "dashboard_planner_token_telemetry_failed",
                extra={"report_id": report_id, "error_code": "dependency_unavailable", "error": str(exc)},
            )
        parsed = _extract_json_object(response.choices[0].message.content or "")
    normalized, rationale, invalid_reason = _resolve_planner_spec(
        parsed,
        base_spec,
        schema,
        title=report.get("title") or "Adaptive dashboard",
        include_guardrail_metadata=True,
    )
    ai_guardrail_decisions = list(normalized.pop("_guardrail_decisions", []))
    fallback_reason = fallback_reason or invalid_reason
    ai_quality = judge_dashboard_quality(
        normalized,
        schema,
        deterministic_plan["intent"],
    )
    deterministic_quality = judge_dashboard_quality(
        deterministic_plan["spec"],
        schema,
        deterministic_plan["intent"],
    )
    # A valid LLM plan is still only a candidate. The deterministic candidate
    # wins when it has materially better semantic fit or readability.
    selected_source = "ai"
    selected_spec = normalized
    if invalid_reason or deterministic_quality["score"] > ai_quality["score"] + 1:
        selected_source = "deterministic"
        selected_spec = deterministic_plan["spec"]
    dashboard = generate_dashboard(
        user_id,
        report_id,
        dashboard_spec=selected_spec,
        persist=False,
        client=client,
    )
    dashboard["planner"] = {
        "model": model,
        "instruction": request_text,
        "fallback": bool(fallback_reason),
        "fallback_reason": fallback_reason,
        "analysis_intent": deterministic_plan["intent"],
        "selected_source": selected_source,
        "candidate_scores": {
            "ai": ai_quality,
            "deterministic": deterministic_quality,
        },
        "guardrails_applied": ai_guardrail_decisions,
        "composition_candidates": deterministic_plan["composition_candidates"],
        "rationale": {
            str(key)[:80]: _text(value, maximum=300)
            for key, value in (
                list(rationale.items())[:MAX_DASHBOARD_WIDGETS]
                if selected_source == "ai"
                else []
            )
        },
    }
    return dashboard


def duplicate_report(
    user_id: str,
    report_id: str,
    *,
    title: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Create an owner-scoped editable copy, including saved chart snapshots."""
    client = client or get_supabase_client()
    original = _owned_report(client, user_id, report_id)
    copy_title = _text(
        title,
        maximum=160,
        fallback=f"{original.get('title') or 'Visualization'} copy",
    )
    payload = {
        "user_id": user_id,
        "conversation_id": original.get("conversation_id"),
        "title": copy_title,
        "description": original.get("description") or "",
        "executive_summary": original.get("executive_summary") or "",
        "dataset_key": original.get("dataset_key"),
        "status": "draft",
        "created_via": "workspace",
        "source_config": original.get("source_config") or {},
        "dashboard_spec": original.get("dashboard_spec") or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    enforce_customer_storage_quota(user_id, _json_size(payload))
    response = client.table("visualization_reports").insert(payload).execute()
    if not response.data:
        raise VisualizationError("Could not duplicate Visualization report")
    duplicated = dict(response.data[0])

    charts_response = (
        client.table("visualization_charts")
        .select("*")
        .eq("report_id", report_id)
        .eq("user_id", user_id)
        .order("sort_order")
        .execute()
    )
    chart_payloads = []
    for chart in charts_response.data or []:
        chart_payloads.append({
            "report_id": duplicated["id"],
            "user_id": user_id,
            "source_message_id": chart.get("source_message_id"),
            "chart_type": chart.get("chart_type"),
            "title": chart.get("title"),
            "subtitle": chart.get("subtitle") or "",
            "config": chart.get("config") or {},
            "data": chart.get("data") or [],
            "insight": chart.get("insight") or "",
            "sort_order": chart.get("sort_order") or 0,
        })
    if chart_payloads:
        enforce_customer_storage_quota(user_id, _json_size(chart_payloads))
        copied_charts = (
            client.table("visualization_charts").insert(chart_payloads).execute()
        )
        duplicated["charts"] = [dict(row) for row in (copied_charts.data or [])]
    else:
        duplicated["charts"] = []
    return duplicated


def list_reports(
    user_id: str,
    *,
    source_message_id: str | None = None,
    client: Any | None = None,
) -> list[dict[str, Any]]:
    client = client or get_supabase_client()
    query = (
        client.table("visualization_reports")
        .select("*")
        .eq("user_id", user_id)
    )
    if source_message_id:
        query = query.eq("source_message_id", source_message_id)
    reports_response = (
        query.order("updated_at", desc=True).limit(MAX_REPORTS).execute()
    )
    reports = [dict(row) for row in (reports_response.data or [])]
    if not reports:
        return []
    report_ids = [str(row["id"]) for row in reports]
    charts_response = (
        client.table("visualization_charts")
        .select("*")
        .eq("user_id", user_id)
        .in_("report_id", report_ids)
        .order("sort_order")
        .order("created_at")
        .execute()
    )
    charts_by_report: dict[str, list[dict[str, Any]]] = {
        report_id: [] for report_id in report_ids
    }
    for chart in charts_response.data or []:
        charts_by_report.setdefault(str(chart["report_id"]), []).append(dict(chart))
    for report in reports:
        report["charts"] = charts_by_report.get(str(report["id"]), [])
    return reports


def create_report(
    user_id: str,
    *,
    title: str,
    description: str = "",
    executive_summary: str = "",
    dataset_key: str | None = None,
    conversation_id: str | None = None,
    created_via: str = "workspace",
    status: str = "draft",
    chart: dict[str, Any] | None = None,
    dashboard_spec: dict[str, Any] | None = None,
    source_message_id: str | None = None,
    source_config: dict[str, Any] | None = None,
    pin: dict[str, Any] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    from app.services.decision_packet import empty_decision_packet, upsert_pin

    client = client or get_supabase_client()
    _trusted_source(
        client,
        user_id,
        conversation_id=conversation_id,
        source_message_id=source_message_id,
    )
    if source_message_id:
        existing_response = (
            client.table("visualization_reports")
            .select("*")
            .eq("user_id", user_id)
            .eq("source_message_id", source_message_id)
            .limit(1)
            .execute()
        )
        if isinstance(existing_response.data, list) and existing_response.data:
            existing_report = dict(existing_response.data[0])
            existing_report["charts"] = existing_report.get("charts") or []
            if pin:
                try:
                    packet = upsert_pin(existing_report.get("decision_packet"), {
                        **pin,
                        "source_message_id": source_message_id,
                        "conversation_id": conversation_id,
                    })
                    existing_report = _persist_decision_packet(
                        client, user_id, str(existing_report["id"]), existing_report, packet,
                    )
                except Exception as exc:
                    logger.warning("decision_pin_on_existing_failed", exc_info=exc)
            existing_report["_created"] = False
            return existing_report
    status = status if status in ALLOWED_REPORT_STATUSES else "draft"
    created_via = created_via if created_via in ALLOWED_CREATED_VIA else "workspace"
    source_config = _normalize_source_config(source_config) or _infer_source_config(
        client, user_id, conversation_id, source_message_id,
    )
    if dashboard_spec and not source_config and not chart:
        raise VisualizationError(
            "Visualization source is missing. Re-run the analysis with the file or connection attached."
        )
    safe_title = _text(title, maximum=160, fallback="Untitled report")
    packet = empty_decision_packet()
    if pin or chart or source_message_id:
        packet = upsert_pin(packet, {
            **(pin or {}),
            "title": (pin or {}).get("title") or safe_title,
            "summary": (pin or {}).get("summary") or executive_summary or "",
            "source_message_id": source_message_id,
            "conversation_id": conversation_id,
            "kind": (pin or {}).get("kind") or ("chart" if chart else "finding"),
        })
    bounded_spec = _bounded_dashboard_spec(
        dashboard_spec,
        title=safe_title,
    )
    if isinstance(bounded_spec, dict):
        bounded_spec = {**bounded_spec, "decision_packet": packet}
    payload = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "source_message_id": source_message_id,
        "title": safe_title,
        "description": _text(description, maximum=4000),
        "executive_summary": _text(executive_summary, maximum=20_000),
        "dataset_key": _text(dataset_key, maximum=500) if dataset_key else None,
        "status": status,
        "created_via": created_via,
        "source_config": source_config,
        "dashboard_spec": bounded_spec,
        "decision_packet": packet,
    }
    normalized_chart = normalize_chart(chart) if chart else None
    enforce_customer_storage_quota(
        user_id,
        _json_size(payload) + (_json_size(normalized_chart) if normalized_chart else 0),
    )
    try:
        response = client.table("visualization_reports").insert(payload).execute()
    except Exception as exc:
        message = str(exc)
        if "decision_packet" not in message and "PGRST204" not in message:
            raise
        payload.pop("decision_packet", None)
        response = client.table("visualization_reports").insert(payload).execute()
    if not response.data:
        raise VisualizationError("Could not create Visualization report")
    report = dict(response.data[0])
    report["decision_packet"] = packet
    report["charts"] = []
    report["_created"] = True
    source_recipe = (source_config or {}).get("cleaning_recipe") or {}
    dataset_version_id = (
        (source_config or {}).get("dataset_version_id")
        or source_recipe.get("dataset_version_id")
    )
    if dataset_version_id:
        from app.services.dataset_catalog import record_dataset_lineage_event

        record_dataset_lineage_event(
            client,
            user_id=user_id,
            dataset_version_id=dataset_version_id,
            event_kind="dashboard_created",
            payload={
                "report_id": report.get("id"),
                "source_message_id": source_message_id,
            },
        )
    if normalized_chart:
        try:
            report["charts"] = [
                add_chart(
                    user_id,
                    str(report["id"]),
                    normalized_chart,
                    source_message_id=source_message_id,
                    skip_quota=True,
                    client=client,
                )
            ]
        except Exception:
            (
                client.table("visualization_reports")
                .delete()
                .eq("id", report["id"])
                .eq("user_id", user_id)
                .execute()
            )
            raise
    return report


def update_report(
    user_id: str,
    report_id: str,
    updates: dict[str, Any],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    from app.services.decision_packet import (
        can_mark_final,
        read_packet_from_report,
        set_insight_action,
        upsert_pin,
    )

    client = client or get_supabase_client()
    report = _owned_report(client, user_id, report_id)
    payload: dict[str, Any] = {}
    if "title" in updates:
        payload["title"] = _text(updates["title"], maximum=160)
        if not payload["title"]:
            raise VisualizationError("Report title is required")
    if "description" in updates:
        payload["description"] = _text(updates["description"], maximum=4000)
    if "executive_summary" in updates:
        payload["executive_summary"] = _text(
            updates["executive_summary"], maximum=20_000
        )
    if "status" in updates:
        status = str(updates["status"] or "")
        if status not in ALLOWED_REPORT_STATUSES:
            raise VisualizationError("Invalid report status")
        if status == "final":
            packet = read_packet_from_report(report)
            story = (report.get("dashboard_spec") or {}).get("story") or {}
            ok, reason = can_mark_final(
                packet,
                has_grounded_story=bool(story.get("evidence_ids") or story.get("evidence") or packet.get("pins")),
                decision_insight_count=len((report.get("dashboard_spec") or {}).get("decision_insights") or []),
            )
            # Also allow final when packet already proved.
            if not ok and packet.get("lifecycle") == "proved":
                ok, reason = True, ""
            if not ok:
                raise VisualizationError(reason)
        payload["status"] = status
    if "filter_state" in updates:
        filter_state = updates["filter_state"]
        if not isinstance(filter_state, dict) or len(filter_state) > 100:
            raise VisualizationError("Invalid dashboard filter state")
        payload["filter_state"] = filter_state
    if "conversation_id" in updates:
        conversation_id = str(updates["conversation_id"] or "").strip()
        if not conversation_id:
            raise VisualizationError("Conversation id is required")
        existing_conversation = str(report.get("conversation_id") or "").strip()
        if existing_conversation and existing_conversation != conversation_id:
            raise VisualizationError(
                "Visualization report is already linked to another conversation"
            )
        _trusted_source(client, user_id, conversation_id=conversation_id)
        payload["conversation_id"] = conversation_id

    packet = read_packet_from_report(report)
    packet_changed = False
    if isinstance(updates.get("pin"), dict):
        packet = upsert_pin(packet, updates["pin"])
        packet_changed = True
    if isinstance(updates.get("insight_action"), dict):
        action = updates["insight_action"]
        packet = set_insight_action(
            packet,
            action_key=str(action.get("action_key") or ""),
            status=str(action.get("status") or "open"),
            note=str(action.get("note") or ""),
            owner=str(action.get("owner") or ""),
            due=action.get("due"),
        )
        packet_changed = True
    if isinstance(updates.get("decision_packet"), dict):
        packet = {**packet, **updates["decision_packet"]}
        packet_changed = True

    if packet_changed and not payload:
        return _persist_decision_packet(client, user_id, report_id, report, packet)

    if not payload and not packet_changed:
        raise VisualizationError("No report fields to update")
    if packet_changed:
        from app.services.decision_packet import packet_persist_payload
        packet_fields = packet_persist_payload(report, packet)
        payload.update(packet_fields)
    else:
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    enforce_customer_storage_quota(user_id, _json_size(payload))
    try:
        response = (
            client.table("visualization_reports")
            .update(payload)
            .eq("id", report_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        message = str(exc)
        if "decision_packet" in message or "PGRST204" in message:
            payload.pop("decision_packet", None)
            response = (
                client.table("visualization_reports")
                .update(payload)
                .eq("id", report_id)
                .eq("user_id", user_id)
                .execute()
            )
        else:
            raise
    if not response.data:
        raise VisualizationError("Could not update Visualization report")
    updated = dict(response.data[0])
    if packet_changed:
        updated["decision_packet"] = packet
    return updated


def reprove_decision_packet(
    user_id: str,
    report_id: str,
    *,
    filters: dict[str, Any] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Force regenerate aggregates, store prove snapshot/diff, clear stale."""
    from app.services.decision_packet import apply_prove, read_packet_from_report, source_fingerprint

    client = client or get_supabase_client()
    report = _owned_report(client, user_id, report_id)
    dashboard = generate_dashboard(
        user_id,
        report_id,
        force=True,
        filters=filters,
        persist=True,
        client=client,
    )
    # Reload after generate mutated source_config / dashboard_spec.
    report = _owned_report(client, user_id, report_id)
    fingerprint = source_fingerprint(dashboard.get("source") or report.get("source_config"))
    packet = apply_prove(
        read_packet_from_report(report),
        fingerprint=fingerprint,
        computed={
            "kpis": dashboard.get("kpis") or [],
            "decision_insights": dashboard.get("decision_insights") or [],
        },
    )
    updated = _persist_decision_packet(client, user_id, report_id, report, packet)
    dashboard = _attach_decision_packet_to_dashboard(updated, dashboard, packet=packet)
    return {
        "report": updated,
        "dashboard": dashboard,
        "prove_diff": (packet.get("last_prove") or {}).get("diff") or [],
    }


def build_chat_visualization_context(
    user_id: str,
    raw_context: Mapping[str, Any],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    """Return bounded owner-verified report context for an AI prompt."""
    client = client or get_supabase_client()
    report_id = str(raw_context.get("report_id") or "").strip()
    if not report_id:
        raise VisualizationError("Visualization report id is required")
    report = _owned_report(client, user_id, report_id)
    spec = report.get("dashboard_spec") or {}
    widgets = list(spec.get("widgets") or []) if isinstance(spec, Mapping) else []
    widget_id = str(raw_context.get("widget_id") or "").strip()
    selected_widget = None
    if widget_id:
        selected_widget = next(
            (
                dict(widget)
                for widget in widgets
                if isinstance(widget, Mapping)
                and str(widget.get("id") or "") == widget_id
            ),
            None,
        )
        if selected_widget is None:
            raise VisualizationError("Visualization widget not found")

    allowed_filter_fields = {
        str(item.get("field") or "")
        for item in list(spec.get("filters") or [])
        if isinstance(item, Mapping) and item.get("field")
    }
    filters = raw_context.get("filters") or {}
    if not isinstance(filters, Mapping) or len(filters) > 100:
        raise VisualizationError("Invalid visualization filters")
    if {str(key) for key in filters} - allowed_filter_fields:
        raise VisualizationError("Visualization filter is not part of this report")

    safe_filters: dict[str, Any] = {}
    for key, value in filters.items():
        if isinstance(value, Mapping):
            safe_filters[str(key)] = {
                str(inner_key)[:40]: str(inner_value)[:200]
                for inner_key, inner_value in list(value.items())[:10]
            }
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe_filters[str(key)] = value if not isinstance(value, str) else value[:200]
        else:
            raise VisualizationError("Invalid visualization filter value")

    safe_widget = None
    if selected_widget:
        safe_widget = {
            key: selected_widget.get(key)
            for key in (
                "id", "kind", "title", "chart_type", "dimension", "measure",
                "aggregation", "time_grain", "columns",
            )
            if selected_widget.get(key) is not None
        }
    source_config = report.get("source_config") or {}
    source_identity = {
        key: str(source_config.get(key) or "")[:500] or None
        for key in ("type", "file_name", "connection_id")
    } if isinstance(source_config, Mapping) else {}
    return {
        "report_id": report_id,
        "title": str(report.get("title") or "")[:160],
        "executive_summary": str(report.get("executive_summary") or "")[:2000],
        "dataset_key": str(report.get("dataset_key") or "")[:500] or None,
        "conversation_id": str(report.get("conversation_id") or "") or None,
        "widget": safe_widget,
        "filters": safe_filters,
        # Used only to enforce explicit-source precedence in ChatContextBuilder;
        # it is removed before the context reaches the model.
        "_source_identity": source_identity,
    }


def add_chart(
    user_id: str,
    report_id: str,
    chart: dict[str, Any],
    *,
    source_message_id: str | None = None,
    skip_quota: bool = False,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or get_supabase_client()
    report = _owned_report(client, user_id, report_id)
    _trusted_source(client, user_id, source_message_id=source_message_id)
    if source_message_id and not (report.get("source_config") or {}):
        message_response = (
            client.table("chat_messages")
            .select("conversation_id")
            .eq("id", source_message_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        conversation_id = (
            (message_response.data or [{}])[0].get("conversation_id")
        )
        inferred_source = _infer_source_config(
            client,
            user_id,
            conversation_id,
            source_message_id,
        )
        if inferred_source:
            (
                client.table("visualization_reports")
                .update({"source_config": inferred_source})
                .eq("id", report_id)
                .eq("user_id", user_id)
                .execute()
            )
    normalized = normalize_chart(chart)
    last = (
        client.table("visualization_charts")
        .select("sort_order")
        .eq("report_id", report_id)
        .eq("user_id", user_id)
        .order("sort_order", desc=True)
        .limit(1)
        .execute()
    )
    last_order = (last.data or [{}])[0].get("sort_order")
    sort_order = (int(last_order) + 1) if last_order is not None else 0
    payload = {
        "report_id": report_id,
        "user_id": user_id,
        "source_message_id": source_message_id,
        **normalized,
        "sort_order": sort_order,
    }
    if not skip_quota:
        enforce_customer_storage_quota(user_id, _json_size(payload))
    response = client.table("visualization_charts").insert(payload).execute()
    if not response.data:
        raise VisualizationError("Could not save chart")
    (
        client.table("visualization_reports")
        .update({"updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", report_id)
        .eq("user_id", user_id)
        .execute()
    )
    return dict(response.data[0])


def delete_report(
    user_id: str, report_id: str, *, client: Any | None = None
) -> None:
    client = client or get_supabase_client()
    _owned_report(client, user_id, report_id)
    (
        client.table("visualization_reports")
        .delete()
        .eq("id", report_id)
        .eq("user_id", user_id)
        .execute()
    )


def delete_chart(
    user_id: str, chart_id: str, *, client: Any | None = None
) -> None:
    client = client or get_supabase_client()
    response = (
        client.table("visualization_charts")
        .delete()
        .eq("id", chart_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        raise VisualizationError("Visualization chart not found")
