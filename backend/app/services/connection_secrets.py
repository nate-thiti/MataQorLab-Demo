"""Application-level encryption and redaction for external connection secrets."""
from __future__ import annotations

import base64
import json
from typing import Any, Dict, Mapping

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

PREFIX = "enc:v1:"
MASK = "••••••••"


class ConnectionSecretError(RuntimeError):
    pass


def _key() -> bytes:
    raw = str(settings.CONNECTION_SECRET_KEY or "").strip()
    if not raw:
        raise ConnectionSecretError("CONNECTION_SECRET_KEY is not configured")
    try:
        key = base64.urlsafe_b64decode(raw.encode("ascii"))
    except Exception as exc:
        raise ConnectionSecretError("CONNECTION_SECRET_KEY must be URL-safe base64") from exc
    if len(key) != 32:
        raise ConnectionSecretError("CONNECTION_SECRET_KEY must decode to exactly 32 bytes")
    return key


def encrypt_text(value: str) -> str:
    nonce = __import__("os").urandom(12)
    encrypted = AESGCM(_key()).encrypt(nonce, str(value or "").encode("utf-8"), None)
    return PREFIX + base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def decrypt_text(value: Any) -> str:
    text = str(value or "")
    if not text.startswith(PREFIX):
        # Legacy rows are readable only for migration continuity. Every
        # backend-managed update rewrites them as authenticated ciphertext.
        return text
    try:
        payload = base64.urlsafe_b64decode(text[len(PREFIX):].encode("ascii"))
        return AESGCM(_key()).decrypt(payload[:12], payload[12:], None).decode("utf-8")
    except Exception as exc:
        raise ConnectionSecretError("Connection secret could not be decrypted") from exc


def encrypt_json(value: Any) -> str:
    return encrypt_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def decrypt_json(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    decoded = json.loads(decrypt_text(value))
    if not isinstance(decoded, dict):
        raise ConnectionSecretError("Encrypted connection payload must be an object")
    return decoded


def hydrate_database_connection(row: Mapping[str, Any]) -> Dict[str, Any]:
    result = dict(row)
    result["password_encrypted"] = decrypt_text(result.get("password_encrypted"))
    return result


def hydrate_api_connection(row: Mapping[str, Any]) -> Dict[str, Any]:
    result = dict(row)
    encrypted = result.get("secrets_encrypted")
    if encrypted:
        secret = decrypt_json(encrypted)
        result["request_headers"] = secret.get("request_headers") or []
        result["request_body"] = secret.get("request_body")
        result["auth_header_name"] = secret.get("auth_header_name") or "Authorization"
        result["auth_header_value"] = secret.get("auth_header_value") or ""
    return result


def _masked_headers(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    return [
        {"key": str(item.get("key") or ""), "value": MASK if item.get("value") else ""}
        for item in value
        if isinstance(item, dict) and str(item.get("key") or "").strip()
    ]


def sanitize_database_connection(row: Mapping[str, Any]) -> Dict[str, Any]:
    allowed = {
        key: row.get(key)
        for key in (
            "id", "provider", "name", "host", "port", "db_name", "username",
            "status", "created_at", "updated_at",
        )
    }
    allowed["password_encrypted"] = MASK if row.get("password_encrypted") else ""
    allowed["has_secret"] = bool(row.get("password_encrypted"))
    return allowed


def sanitize_api_connection(row: Mapping[str, Any]) -> Dict[str, Any]:
    hydrated = hydrate_api_connection(row)
    allowed = {
        key: hydrated.get(key)
        for key in ("id", "name", "method", "url", "status", "created_at", "updated_at")
    }
    allowed["request_headers"] = _masked_headers(hydrated.get("request_headers"))
    allowed["request_body"] = None
    allowed["auth_header_name"] = hydrated.get("auth_header_name") or "Authorization"
    allowed["auth_header_value"] = MASK if hydrated.get("auth_header_value") else ""
    allowed["has_secret"] = bool(
        hydrated.get("request_headers") or hydrated.get("request_body")
        or hydrated.get("auth_header_value")
    )
    return allowed


def api_secret_payload(connection: Mapping[str, Any]) -> str:
    return encrypt_json({
        "request_headers": connection.get("request_headers") or [],
        "request_body": connection.get("request_body"),
        "auth_header_name": connection.get("auth_header_name") or "Authorization",
        "auth_header_value": connection.get("auth_header_value") or "",
    })
