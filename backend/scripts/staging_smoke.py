"""Read-only staging smoke checks for Supabase Data API, Storage, RLS, and P0 hardening."""
from __future__ import annotations

import os
import sys

import requests


ENCRYPTED_SECRET_PREFIX = "enc:v1:"


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _get(url: str, key: str, path: str, *, token: str | None = None) -> requests.Response:
    headers = {"apikey": key, "Authorization": f"Bearer {token or key}"}
    return requests.get(f"{url.rstrip('/')}{path}", headers=headers, timeout=30)


def _assert_denied(response: requests.Response, resource: str) -> None:
    if response.status_code not in {401, 403, 404}:
        raise RuntimeError(
            f"{resource} must be unavailable to browser roles; got HTTP {response.status_code}"
        )


def _assert_encrypted(value: object, resource: str) -> None:
    if not str(value or "").startswith(ENCRYPTED_SECRET_PREFIX):
        raise RuntimeError(f"{resource} still contains a legacy plaintext secret")


def main() -> int:
    url = _required("STAGING_SUPABASE_URL")
    anon_key = _required("STAGING_SUPABASE_ANON_KEY")
    service_key = _required("STAGING_SUPABASE_SERVICE_ROLE_KEY")

    plans = _get(url, service_key, "/rest/v1/plans?select=id&limit=1")
    plans.raise_for_status()

    buckets = _get(url, service_key, "/storage/v1/bucket")
    buckets.raise_for_status()
    bucket_ids = {item.get("id") for item in buckets.json()}
    if "business-data" not in bucket_ids:
        raise RuntimeError("business-data storage bucket is missing")

    database_connections = _get(
        url,
        service_key,
        "/rest/v1/database_connections?select=id,password_encrypted&limit=1000",
    )
    database_connections.raise_for_status()
    for row in database_connections.json():
        _assert_encrypted(
            row.get("password_encrypted"),
            f"database_connections/{row.get('id')}/password_encrypted",
        )

    api_connections = _get(
        url,
        service_key,
        (
            "/rest/v1/api_connections"
            "?select=id,secrets_encrypted,secret_version,request_headers,request_body,"
            "auth_header_value&limit=1000"
        ),
    )
    api_connections.raise_for_status()
    for row in api_connections.json():
        _assert_encrypted(
            row.get("secrets_encrypted"),
            f"api_connections/{row.get('id')}/secrets_encrypted",
        )
        if int(row.get("secret_version") or 0) < 1:
            raise RuntimeError(f"api_connections/{row.get('id')} has no encrypted secret version")
        if row.get("request_body") or row.get("auth_header_value"):
            raise RuntimeError(f"api_connections/{row.get('id')} exposes legacy plaintext fields")
        if any(
            str(item.get("value") or "")
            for item in (row.get("request_headers") or [])
            if isinstance(item, dict)
        ):
            raise RuntimeError(f"api_connections/{row.get('id')} exposes plaintext header values")

    setup_schema = _get(
        url,
        service_key,
        "/rest/v1/data_setup_sessions?select=id,recipe_hash,contract_hash&limit=0",
    )
    setup_schema.raise_for_status()

    anonymous_profiles = _get(url, anon_key, "/rest/v1/profiles?select=id&limit=1")
    if anonymous_profiles.status_code not in {200, 401, 403}:
        anonymous_profiles.raise_for_status()
    if anonymous_profiles.status_code == 200 and anonymous_profiles.json():
        raise RuntimeError("anonymous request could read protected profile rows")

    _assert_denied(
        _get(url, anon_key, "/rest/v1/database_connections?select=id&limit=1"),
        "database_connections",
    )
    _assert_denied(
        _get(url, anon_key, "/rest/v1/api_connections?select=id&limit=1"),
        "api_connections",
    )

    user_jwt = os.getenv("STAGING_TEST_USER_JWT", "").strip()
    if user_jwt:
        user_response = _get(url, anon_key, "/auth/v1/user", token=user_jwt)
        user_response.raise_for_status()
        user_id = user_response.json().get("id")
        profile_response = _get(
            url,
            anon_key,
            "/rest/v1/profiles?select=id&limit=5",
            token=user_jwt,
        )
        profile_response.raise_for_status()
        if any(row.get("id") != user_id for row in profile_response.json()):
            raise RuntimeError("authenticated RLS smoke returned another user's profile")
        _assert_denied(
            _get(
                url,
                anon_key,
                "/rest/v1/database_connections?select=id&limit=1",
                token=user_jwt,
            ),
            "database_connections",
        )
        _assert_denied(
            _get(
                url,
                anon_key,
                "/rest/v1/api_connections?select=id&limit=1",
                token=user_jwt,
            ),
            "api_connections",
        )

    print("Staging Supabase and P0 hardening smoke checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

