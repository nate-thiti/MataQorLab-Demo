"""HTTP client helpers for user-configured REST API connections."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional

import requests

from app.services.network_security import validate_outbound_url, validated_redirect_url


def normalize_header_items(items: Optional[List[Any]]) -> List[Dict[str, str]]:
    """Return [{key, value}, ...] with non-empty keys."""
    if not items:
        return []
    normalized: List[Dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            value = item.get("value")
            normalized.append({"key": key, "value": "" if value is None else str(value)})
    return normalized


def build_request_headers(conn: Mapping[str, Any]) -> Dict[str, str]:
    """Merge request_headers JSON with legacy auth_header_name/value."""
    headers: Dict[str, str] = {}
    for item in normalize_header_items(conn.get("request_headers")):
        headers[item["key"]] = item["value"]

    if not headers:
        name = (conn.get("auth_header_name") or "").strip()
        value = conn.get("auth_header_value")
        if name and value is not None and str(value) != "":
            headers[name] = str(value)
    return headers


def parse_request_body(raw: Any) -> Optional[Any]:
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        return json.loads(text)
    if isinstance(raw, (dict, list)):
        if isinstance(raw, dict) and not raw:
            return None
        return raw
    return None


def _ensure_json_content_type(headers: Dict[str, str]) -> Dict[str, str]:
    if any(k.lower() == "content-type" for k in headers):
        return headers
    return {**headers, "Content-Type": "application/json"}


def fetch_external_api(
    *,
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    body: Any = None,
    timeout: float = 15,
) -> requests.Response:
    """Execute GET/POST/PUT/PATCH against an external REST endpoint."""
    req_headers = dict(headers or {})
    verb = (method or "GET").upper()
    json_body = None
    data_body = None

    if verb in {"POST", "PUT", "PATCH"} and body is not None:
        parsed = parse_request_body(body)
        if parsed is not None:
            req_headers = _ensure_json_content_type(req_headers)
            json_body = parsed

    current_url = validate_outbound_url(url)
    for _ in range(6):
        kwargs = {
            "headers": req_headers,
            "timeout": timeout,
            "allow_redirects": False,
        }
        if verb in {"POST", "PUT", "PATCH"}:
            kwargs["json"] = json_body
        if verb == "POST":
            response = requests.post(current_url, **kwargs)
        elif verb == "PUT":
            response = requests.put(current_url, **kwargs)
        elif verb == "PATCH":
            response = requests.patch(current_url, **kwargs)
        else:
            response = requests.get(current_url, **kwargs)
        if int(response.status_code) not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("location")
        if not location:
            return response
        current_url = validated_redirect_url(current_url, location)
        if int(response.status_code) == 303:
            verb = "GET"
            json_body = None
    raise ValueError("API redirect limit exceeded")


def fetch_from_connection(conn: Mapping[str, Any], *, timeout: float = 15) -> requests.Response:
    """Fetch using a stored api_connections row (first page only)."""
    from app.services.api_pagination import body_without_pagination, get_pagination_config

    method = conn.get("method", "GET")
    url = conn.get("url")
    if not url:
        raise ValueError("API connection URL is required")

    headers = build_request_headers(conn)
    body = body_without_pagination(conn) if get_pagination_config(conn) else conn.get("request_body")
    response = fetch_external_api(
        method=method,
        url=url,
        headers=headers,
        body=body,
        timeout=timeout,
    )
    response.raise_for_status()
    return response
