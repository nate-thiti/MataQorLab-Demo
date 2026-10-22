"""Internal workflow artifacts (not published dataset versions)."""
from __future__ import annotations

import os
import tempfile
import logging
from typing import Optional

from app.core.config import settings
from app.core.supabase import get_supabase_client
from app.services.dataset_engine import DatasetHandle, TABLE_NAME
from app.services.dataset_loader import load_handle_from_storage
from app.services.storage_quota import enforce_customer_storage_quota

logger = logging.getLogger(__name__)


def cleaned_artifact_name(session_id: str, version: int = 1) -> str:
    return f"data_setup_{session_id}_cleaned_v{int(version)}.parquet"


def persist_cleaned_handle(
    user_id: str,
    session_id: str,
    handle: DatasetHandle,
    *,
    version: int = 1,
) -> str:
    """Write a private cleaned parquet for restart-safe clean resume.

    This is an internal workflow artifact — not a published DatasetVersion.
    """
    export_handle = DatasetHandle.for_sql_execution(handle)
    path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            path = tmp.name
        escaped = path.replace("'", "''")
        export_handle._con.execute(
            f"COPY (SELECT * FROM {TABLE_NAME}) TO '{escaped}' "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        storage_name = cleaned_artifact_name(session_id, version)
        storage_path = f"{user_id}/{storage_name}"
        enforce_customer_storage_quota(user_id, os.path.getsize(path), storage_path)
        with open(path, "rb") as upload:
            get_supabase_client().storage.from_(settings.AGENT_SESSION_STORAGE_BUCKET).upload(
                path=storage_path,
                file=upload,
                file_options={
                    "content-type": "application/octet-stream",
                    "upsert": "true",
                },
            )
        return storage_name
    finally:
        if path and os.path.exists(path):
            os.unlink(path)


def load_cleaned_artifact(user_id: str, artifact_key: str) -> Optional[DatasetHandle]:
    """Load a restart-safe cleaned artifact when it is still retained.

    The artifact is an optimization, not the authoritative source.  A storage
    lifecycle rule or a manual cleanup can remove it after ``clean`` was
    recorded as completed; callers must then rebuild from the original source
    instead of turning that recoverable condition into a permanent finalize
    retry loop.
    """
    if not artifact_key:
        return None
    try:
        return load_handle_from_storage(user_id, artifact_key, None)
    except Exception as exc:
        detail = str(exc).lower()
        missing = (
            "object not found" in detail
            or "nosuchkey" in detail
            or ("not_found" in detail and "404" in detail)
        )
        if not missing:
            raise
        logger.warning(
            "cleaned_artifact_missing_rebuild_required",
            extra={"artifact_key": artifact_key, "user_id": user_id},
        )
        return None
