"""One-time migration of legacy plaintext connector secrets.

Run from backend after configuring CONNECTION_SECRET_KEY:
    python scripts/reencrypt_connection_secrets.py
"""
from app.core.supabase import get_supabase_client
from app.services.connection_secrets import (
    PREFIX,
    api_secret_payload,
    encrypt_text,
    hydrate_api_connection,
)


def main() -> None:
    client = get_supabase_client()
    database_rows = client.table("database_connections").select("*").execute().data or []
    api_rows = client.table("api_connections").select("*").execute().data or []

    database_updated = 0
    for row in database_rows:
        password = str(row.get("password_encrypted") or "")
        if password.startswith(PREFIX):
            continue
        client.table("database_connections").update({
            "password_encrypted": encrypt_text(password),
        }).eq("id", row["id"]).execute()
        database_updated += 1

    api_updated = 0
    for row in api_rows:
        if row.get("secrets_encrypted"):
            continue
        hydrated = hydrate_api_connection(row)
        headers = hydrated.get("request_headers") or []
        client.table("api_connections").update({
            "secrets_encrypted": api_secret_payload(hydrated),
            "secret_version": 1,
            "request_headers": [
                {"key": item.get("key"), "value": ""}
                for item in headers if isinstance(item, dict) and item.get("key")
            ],
            "request_body": None,
            "auth_header_value": "",
        }).eq("id", row["id"]).execute()
        api_updated += 1

    print(f"Encrypted {database_updated} database and {api_updated} API connections.")


if __name__ == "__main__":
    main()
