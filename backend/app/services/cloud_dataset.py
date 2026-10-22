"""Provider-aware, transient downloads for linked tabular datasets."""
from __future__ import annotations

import base64
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse

import requests

from app.core.config import settings
from app.services.dataset_loader import DatasetLoadError, _ingest_from_path
from app.services.file_validation import FileValidationError, validate_upload_bytes
from app.services.network_security import validate_outbound_url

SUPPORTED_EXTENSIONS = {"csv", "json", "ndjson", "xlsx", "xls", "parquet"}
GOOGLE_HOSTS = {"docs.google.com", "drive.google.com", "www.googleapis.com"}
MICROSOFT_HOST_SUFFIXES = (
    "1drv.ms",
    "1drv.com",
    "onedrive.live.com",
    "storage.live.com",
    "sharepoint.com",
    "sharepoint-df.com",
)


def _allowed_host(provider: str, host: str) -> bool:
    host = host.lower().rstrip(".")
    if provider == "google":
        return host in GOOGLE_HOSTS or host.endswith(".googleusercontent.com")
    if provider == "microsoft":
        return any(host == suffix or host.endswith(f".{suffix}") for suffix in MICROSOFT_HOST_SUFFIXES)
    return False


def _google_download_url(source_url: str, sheet_name: Optional[str] = None) -> str:
    parsed = urlparse(source_url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower() == "docs.google.com" and "spreadsheets" in parts and "d" in parts:
        file_id = parts[parts.index("d") + 1]
        query = parse_qs(parsed.query)
        gid = (query.get("gid") or [None])[0]
        if not gid and parsed.fragment.startswith("gid="):
            gid = parsed.fragment.split("=", 1)[1]
        params = {"format": "xlsx"}
        if sheet_name:
            params["sheet"] = sheet_name
        elif gid:
            params["gid"] = gid
        return f"https://docs.google.com/spreadsheets/d/{quote(file_id)}/export?{urlencode(params)}"
    if parsed.netloc.lower() == "drive.google.com" and "d" in parts:
        file_id = parts[parts.index("d") + 1]
        return f"https://drive.google.com/uc?export=download&id={quote(file_id)}"
    return source_url


def normalize_download_url(provider: str, source_url: str, sheet_name: Optional[str] = None) -> str:
    provider = provider.strip().lower()
    parsed = urlparse(source_url.strip())
    if parsed.scheme != "https" or not parsed.hostname or not _allowed_host(provider, parsed.hostname):
        raise ValueError("Only HTTPS Google Drive/Sheets or Microsoft OneDrive/SharePoint links are allowed")
    if provider == "google":
        return _google_download_url(source_url, sheet_name)
    query = parse_qs(parsed.query)
    query["download"] = ["1"]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True), fragment=""))


def _download_with_safe_redirects(provider: str, url: str) -> tuple[str, Dict[str, str]]:
    current = url
    headers: Dict[str, str] = {}
    fd, path = tempfile.mkstemp(suffix=".cloud")
    os.close(fd)
    try:
        with open(path, "wb") as destination:
            for _ in range(6):
                validate_outbound_url(current)
                parsed = urlparse(current)
                if not parsed.hostname or not _allowed_host(provider, parsed.hostname):
                    raise DatasetLoadError("Cloud provider redirected to an untrusted host")
                response = requests.get(
                    current,
                    stream=True,
                    allow_redirects=False,
                    timeout=settings.STORAGE_DOWNLOAD_TIMEOUT_SECONDS,
                )
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise DatasetLoadError("Cloud provider returned an invalid redirect")
                    current = requests.compat.urljoin(current, location)
                    continue
                response.raise_for_status()
                total = 0
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    validate_upload_bytes("cloud_dataset", total)
                    destination.write(chunk)
                headers = {key.lower(): value for key, value in response.headers.items()}
                break
            else:
                raise DatasetLoadError("Too many cloud provider redirects")
        return path, headers
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def _extension(display_name: str, content_type: str, provider: str) -> str:
    ext = Path(display_name).suffix.lower().lstrip(".")
    if ext in SUPPORTED_EXTENSIONS:
        return ext
    content_type = content_type.split(";", 1)[0].lower()
    mapping = {
        "text/csv": "csv",
        "application/json": "json",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "application/vnd.ms-excel": "xls",
        "application/vnd.apache.parquet": "parquet",
    }
    if content_type in mapping:
        return mapping[content_type]
    if provider == "google":
        return "xlsx"
    raise DatasetLoadError("Could not determine the linked file type")


def load_cloud_handle(connection: Dict[str, Any]):
    """Download a linked file transiently and return a DatasetHandle plus sync metadata."""
    provider = str(connection.get("provider") or "").lower()
    source_url = str(connection.get("source_url") or "")
    display_name = str(connection.get("display_name") or "cloud_dataset")
    download_url = normalize_download_url(provider, source_url, connection.get("sheet_name"))
    path = None
    renamed = None
    try:
        path, headers = _download_with_safe_redirects(provider, download_url)
        ext = _extension(display_name, headers.get("content-type", ""), provider)
        renamed = f"{path}.{ext}"
        os.replace(path, renamed)
        path = None
        size = os.path.getsize(renamed)
        validate_upload_bytes(f"{display_name}.{ext}", size)
        digest = hashlib.sha256()
        with open(renamed, "rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        handle = _ingest_from_path(renamed, f"{display_name}.{ext}", None, connection.get("json_path"))
        if handle is None:
            raise DatasetLoadError("Unsupported linked tabular file")
        return handle, {
            "content_hash": digest.hexdigest(),
            "etag": headers.get("etag"),
            "last_modified": headers.get("last-modified"),
            "size_bytes": size,
            "file_type": ext,
        }
    except (requests.RequestException, FileValidationError, ValueError) as exc:
        raise DatasetLoadError(str(exc)) from exc
    finally:
        for candidate in (path, renamed):
            if candidate and os.path.exists(candidate):
                try:
                    os.unlink(candidate)
                except OSError:
                    pass


def microsoft_share_id(source_url: str) -> str:
    """Return the Graph shares API token for future private-link OAuth support."""
    encoded = base64.urlsafe_b64encode(source_url.encode()).decode().rstrip("=")
    return f"u!{encoded}"
