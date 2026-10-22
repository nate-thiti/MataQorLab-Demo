"""Paginated REST API fetch — stream records to NDJSON without holding full payload in RAM."""
from __future__ import annotations

import copy
import json
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.core.config import settings
from app.services.external_api import (
    build_request_headers,
    fetch_external_api,
    parse_request_body,
)
from app.services.json_structure import flatten_json_to_records

PAGINATION_KEY = "_pagination"


def get_pagination_config(conn: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    pag = conn.get("pagination")
    if isinstance(pag, dict) and pag:
        return pag
    body = conn.get("request_body")
    if isinstance(body, dict) and isinstance(body.get(PAGINATION_KEY), dict):
        return body[PAGINATION_KEY]
    return None


def body_without_pagination(conn: Mapping[str, Any]) -> Optional[Any]:
    body = conn.get("request_body")
    if not isinstance(body, dict):
        return body
    return {k: v for k, v in body.items() if k != PAGINATION_KEY}


def get_nested(data: Any, path: str) -> Any:
    if not path:
        return data
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def extract_records(data: Any, records_path: str = "") -> List[dict]:
    if records_path:
        node = get_nested(data, records_path)
        if isinstance(node, list):
            return [x for x in node if isinstance(x, dict)]
        if isinstance(node, dict):
            return [node]
        return []
    return flatten_json_to_records(data)


def _merge_query(url: str, params: Dict[str, Any]) -> str:
    parsed = urlparse(url)
    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key, value in params.items():
        existing[str(key)] = str(value)
    new_query = urlencode(existing)
    return urlunparse(parsed._replace(query=new_query))


def _fetch_page(
    *,
    method: str,
    url: str,
    headers: Dict[str, str],
    body: Any,
    timeout: float,
) -> Any:
    response = fetch_external_api(
        method=method,
        url=url,
        headers=headers,
        body=body,
        timeout=timeout,
    )
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return {"raw_response": response.text}


def iter_api_records(
    conn: Mapping[str, Any],
    *,
    timeout: Optional[float] = None,
) -> Iterator[dict]:
    """Yield row dicts from a connection; uses pagination config when present."""
    pag = get_pagination_config(conn)
    method = str(conn.get("method") or "GET").upper()
    base_url = str(conn.get("url") or "")
    if not base_url:
        raise ValueError("API connection URL is required")

    headers = build_request_headers(conn)
    base_body = body_without_pagination(conn)
    req_timeout = timeout if timeout is not None else float(settings.API_FETCH_TIMEOUT_SECONDS)

    if not pag:
        data = _fetch_page(
            method=method,
            url=base_url,
            headers=headers,
            body=base_body,
            timeout=req_timeout,
        )
        for rec in extract_records(data, ""):
            yield rec
        return

    style = str(pag.get("style") or "offset").lower()
    page_size = int(pag.get("page_size") or 1000)
    max_pages = int(pag.get("max_pages") or settings.API_PAGINATION_MAX_PAGES)
    max_rows = int(pag.get("max_rows") or settings.SQL_SYNC_ROW_LIMIT)
    records_path = str(pag.get("records_path") or "")
    param_location = str(pag.get("param_location") or ("body" if method in {"POST", "PUT", "PATCH"} else "query"))

    emitted = 0

    if style == "next_url":
        url = base_url
        for _ in range(max_pages):
            data = _fetch_page(
                method=method,
                url=url,
                headers=headers,
                body=base_body,
                timeout=req_timeout,
            )
            for rec in extract_records(data, records_path):
                yield rec
                emitted += 1
                if emitted >= max_rows:
                    return
            next_url = get_nested(data, str(pag.get("next_url_path") or "next"))
            if not next_url or not isinstance(next_url, str):
                return
            url = next_url
            method = "GET"
            base_body = None
        return

    if style == "page":
        page_param = str(pag.get("page_param") or "page")
        start_page = int(pag.get("start_page") or 1)
        for page_num in range(start_page, start_page + max_pages):
            params = {page_param: page_num, str(pag.get("limit_param") or "limit"): page_size}
            url = _merge_query(base_url, params) if param_location == "query" else base_url
            body = base_body
            if param_location == "body":
                body = copy.deepcopy(base_body) if isinstance(base_body, dict) else {}
                if not isinstance(body, dict):
                    body = {}
                body.update(params)
            data = _fetch_page(method=method, url=url, headers=headers, body=body, timeout=req_timeout)
            records = extract_records(data, records_path)
            if not records:
                return
            for rec in records:
                yield rec
                emitted += 1
                if emitted >= max_rows:
                    return
        return

    # offset (default)
    offset_param = str(pag.get("offset_param") or "offset")
    limit_param = str(pag.get("limit_param") or "limit")
    offset = int(pag.get("start_offset") or 0)
    for _ in range(max_pages):
        params = {offset_param: offset, limit_param: page_size}
        url = _merge_query(base_url, params) if param_location == "query" else base_url
        body = base_body
        if param_location == "body":
            body = copy.deepcopy(base_body) if isinstance(base_body, dict) else {}
            if not isinstance(body, dict):
                body = {}
            body.update(params)
        data = _fetch_page(method=method, url=url, headers=headers, body=body, timeout=req_timeout)
        records = extract_records(data, records_path)
        if not records:
            return
        for rec in records:
            yield rec
            emitted += 1
            if emitted >= max_rows:
                return
        if len(records) < page_size:
            return
        offset += page_size


def stream_api_records_to_ndjson(
    conn: Mapping[str, Any],
    output_path: str,
    *,
    timeout: Optional[float] = None,
    on_page: Optional[Callable[[int], None]] = None,
) -> int:
    """Write API records to NDJSON; returns row count."""
    count = 0
    page_size = int((get_pagination_config(conn) or {}).get("page_size") or 1000)
    with open(output_path, "w", encoding="utf-8") as handle:
        for rec in iter_api_records(conn, timeout=timeout):
            handle.write(json.dumps(rec, ensure_ascii=False, default=str))
            handle.write("\n")
            count += 1
            if on_page and count % max(1, page_size) == 0:
                on_page(count // max(1, page_size))
    return count


def fetch_connection_json(conn: Mapping[str, Any], *, timeout: Optional[float] = None) -> Any:
    """Single-page fetch (legacy); prefer iter_api_records for large APIs."""
    pag = get_pagination_config(conn)
    if pag:
        records = list(iter_api_records(conn, timeout=timeout))
        if records:
            return records
    method = str(conn.get("method") or "GET").upper()
    url = str(conn.get("url") or "")
    headers = build_request_headers(conn)
    body = body_without_pagination(conn)
    req_timeout = timeout if timeout is not None else float(settings.API_FETCH_TIMEOUT_SECONDS)
    return _fetch_page(method=method, url=url, headers=headers, body=body, timeout=req_timeout)
