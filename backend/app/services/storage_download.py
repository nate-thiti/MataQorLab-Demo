"""Download files from Supabase Storage — stream to disk without holding full bytes in RAM."""

import os
import tempfile
from typing import Optional

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.supabase import get_supabase_client


class FileAttachmentError(Exception):
    """User-uploaded file could not be loaded from storage."""


def _is_retryable_storage_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return (
        "timeout" in msg
        or "timed out" in msg
        or "connection" in msg
        or "503" in msg
        or "502" in msg
    )


def _extract_signed_url(payload: object) -> Optional[str]:
    if isinstance(payload, dict):
        return (
            payload.get("signedURL")
            or payload.get("signedUrl")
            or payload.get("signed_url")
        )
    for key in ("signedURL", "signedUrl", "signed_url"):
        value = getattr(payload, key, None)
        if value:
            return str(value)
    return None


def get_storage_object_size(bucket: str, storage_path: str) -> Optional[int]:
    """Return object size in bytes from storage list metadata (no download)."""
    parts = storage_path.rsplit("/", 1)
    if len(parts) != 2:
        return None
    folder, name = parts
    try:
        supabase = get_supabase_client()
        entries = supabase.storage.from_(bucket).list(folder) or []
        for entry in entries:
            if entry.get("name") == name:
                meta = entry.get("metadata") or {}
                size = meta.get("size") or entry.get("size")
                if size is not None:
                    return int(size)
    except Exception as e:
        print(f"Storage metadata lookup failed ({bucket}/{storage_path}): {e}")
    return None


def get_storage_object_metadata(bucket: str, storage_path: str) -> dict:
    """Return bounded object metadata used by freshness and cost guardrails."""
    parts = storage_path.rsplit("/", 1)
    if len(parts) != 2:
        return {}
    folder, name = parts
    try:
        entries = get_supabase_client().storage.from_(bucket).list(folder) or []
        for entry in entries:
            if entry.get("name") != name:
                continue
            metadata = entry.get("metadata") or {}
            return {
                "size": metadata.get("size") or entry.get("size"),
                "updated_at": (
                    entry.get("updated_at")
                    or entry.get("updatedAt")
                    or entry.get("created_at")
                    or entry.get("createdAt")
                ),
            }
    except Exception as exc:
        print(f"Storage metadata lookup failed ({bucket}/{storage_path}): {exc}")
    return {}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable_storage_error),
    reraise=True,
)
def _stream_signed_url_to_path(url: str, dest: str) -> None:
    timeout = httpx.Timeout(float(settings.STORAGE_DOWNLOAD_TIMEOUT_SECONDS))
    with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as response:
        response.raise_for_status()
        with open(dest, "wb") as out:
            for chunk in response.iter_bytes(65536):
                out.write(chunk)


def download_storage_to_path(bucket: str, storage_path: str, *, suffix: str = "") -> str:
    """Stream a storage object to a temp file; caller deletes dest when done."""
    supabase = get_supabase_client()
    signed = supabase.storage.from_(bucket).create_signed_url(storage_path, 3600)
    url = _extract_signed_url(signed)
    if not url:
        raise FileAttachmentError(f"Could not create signed URL for {storage_path}")

    fd, dest = tempfile.mkstemp(suffix=suffix or os.path.splitext(storage_path)[1])
    os.close(fd)
    try:
        _stream_signed_url_to_path(url, dest)
    except Exception:
        try:
            os.unlink(dest)
        except OSError:
            pass
        raise
    return dest


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable_storage_error),
    reraise=True,
)
def _download_bytes(bucket: str, file_path: str) -> bytes:
    """Legacy full download — prefer download_storage_to_path for large files."""
    path = download_storage_to_path(bucket, file_path)
    try:
        with open(path, "rb") as handle:
            return handle.read()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def download_business_data_file(user_id: str, file_name: str) -> bytes:
    file_path = f"{user_id}/{file_name}"
    return _download_bytes(settings.AGENT_SESSION_STORAGE_BUCKET, file_path)


def download_business_data_file_safe(user_id: str, file_name: str) -> Optional[bytes]:
    file_path = f"{user_id}/{file_name}"
    return download_storage_path_safe(settings.AGENT_SESSION_STORAGE_BUCKET, file_path)


def download_business_data_to_path(
    user_id: str,
    file_name: str,
    *,
    suffix: str = "",
) -> str:
    storage_path = f"{user_id}/{file_name}"
    return download_storage_to_path(
        settings.AGENT_SESSION_STORAGE_BUCKET,
        storage_path,
        suffix=suffix or os.path.splitext(file_name)[1],
    )


def download_storage_path(bucket: str, file_path: str) -> bytes:
    return _download_bytes(bucket, file_path)


def download_storage_path_safe(bucket: str, file_path: str) -> Optional[bytes]:
    try:
        return _download_bytes(bucket, file_path)
    except Exception as e:
        print(f"Storage download failed ({bucket}/{file_path}): {e}")
        return None
