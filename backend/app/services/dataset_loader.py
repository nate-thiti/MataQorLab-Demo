"""Load DatasetHandle from Supabase Storage without holding full file bytes in memory."""
from __future__ import annotations

import os
from typing import List, Optional

from app.core.config import settings
from app.core.supabase import get_supabase_client
from app.services.dataset_engine import DatasetHandle
from app.services.dataset_ingest_cache import (
    lookup_storage_size,
    persist_ingest_cache,
    try_load_cached_handle,
)
from app.services.file_validation import FileValidationError, validate_upload_bytes
from app.services.large_data_ingest import ingest_excel_path, ingest_json_path
from app.services.storage_download import download_business_data_to_path
from app.services.storage_download import get_storage_object_metadata


class DatasetLoadError(Exception):
    """Failed to load or validate a dataset from storage."""


def _ingest_from_path(
    path: str,
    file_name: str,
    target_cols: Optional[List[str]],
    json_path: Optional[str] = None,
) -> Optional[DatasetHandle]:
    ext = file_name.rsplit(".", 1)[-1].lower()
    if ext in ("csv", "parquet"):
        return DatasetHandle.from_file_path(path, file_name, target_cols, cleanup_path=False)
    if ext in ("xlsx", "xls"):
        return ingest_excel_path(path, target_cols)
    if ext in ("json", "ndjson"):
        return ingest_json_path(path, target_cols, json_path)
    return None


def load_handle_from_storage(
    user_id: str,
    file_name: str,
    target_cols: Optional[List[str]] = None,
    json_path: Optional[str] = None,
) -> Optional[DatasetHandle]:
    storage_file_name = file_name
    cache_identity = file_name
    if file_name.startswith("etl:"):
        response = (
            get_supabase_client()
            .table("etl_schedules")
            .select("latest_output_file,latest_output_version")
            .eq("user_id", user_id)
            .eq("output_dataset_key", file_name)
            .limit(1)
            .execute()
        )
        schedule = (response.data or [{}])[0]
        storage_file_name = str(schedule.get("latest_output_file") or "")
        if not storage_file_name:
            raise DatasetLoadError(
                "ETL dataset has no completed output yet. Run the schedule first."
            )
        cache_identity = (
            f"{file_name}@{schedule.get('latest_output_version') or storage_file_name}"
        )

    ext = storage_file_name.rsplit(".", 1)[-1].lower()
    if ext not in ("csv", "parquet", "xlsx", "xls", "json", "ndjson"):
        return None

    object_metadata = get_storage_object_metadata(
        settings.AGENT_SESSION_STORAGE_BUCKET,
        f"{user_id}/{storage_file_name}",
    )
    raw_file_size = object_metadata.get("size") or lookup_storage_size(user_id, storage_file_name)
    file_size = int(raw_file_size) if raw_file_size is not None else None
    source_fingerprint = "|".join(
        str(value or "")
        for value in (
            cache_identity,
            file_size,
            object_metadata.get("updated_at"),
        )
    )
    if file_size is not None and not json_path:
        validate_upload_bytes(storage_file_name, file_size)
        cached = try_load_cached_handle(
            user_id, cache_identity, file_size, source_fingerprint
        )
        if cached is not None:
            return cached

    path: Optional[str] = None
    try:
        path = download_business_data_to_path(
            user_id,
            storage_file_name,
            suffix=f".{ext}",
        )
        size = file_size if file_size is not None else os.path.getsize(path)
        validate_upload_bytes(storage_file_name, size)

        if file_size is None and not json_path:
            cached = try_load_cached_handle(
                user_id, cache_identity, size, source_fingerprint
            )
            if cached is not None:
                return cached

        handle = _ingest_from_path(
            path,
            storage_file_name,
            target_cols,
            json_path,
        )
        if handle is not None and size is not None and not json_path:
            handle._source_fingerprint = source_fingerprint
            persist_ingest_cache(
                user_id, cache_identity, size, handle, source_fingerprint
            )
        elif handle is not None:
            handle._source_fingerprint = source_fingerprint
        return handle
    except FileValidationError as exc:
        raise DatasetLoadError(str(exc)) from exc
    finally:
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass


def load_json_attachment_from_storage(user_id: str, file_name: str):
    """Load raw JSON for non-tabular preview paths (small files only)."""
    path: Optional[str] = None
    try:
        path = download_business_data_to_path(user_id, file_name, suffix=".json")
        size = os.path.getsize(path)
        if size > 512_000:
            raise DatasetLoadError(
                "JSON file too large for inline preview; use server-side ingest."
            )
        import json

        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    finally:
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass
