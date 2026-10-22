import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock

from app.core.auth import require_matching_user_id, validate_supabase_storage_url
from app.api.routes import _trusted_conversation_id


def test_require_matching_user_id_accepts_match():
    assert require_matching_user_id("user-a", "user-a") == "user-a"


def test_require_matching_user_id_rejects_mismatch():
    with pytest.raises(HTTPException) as exc:
        require_matching_user_id("user-a", "user-b")
    assert exc.value.status_code == 403


def test_validate_supabase_storage_url_accepts_signed_path(monkeypatch):
    monkeypatch.setattr(
        "app.core.auth.settings.SUPABASE_URL",
        "https://abc.supabase.co",
    )
    validate_supabase_storage_url(
        "https://abc.supabase.co/storage/v1/object/sign/business-data/user/file.parquet?token=x"
    )


def test_validate_supabase_storage_url_rejects_foreign_host(monkeypatch):
    monkeypatch.setattr(
        "app.core.auth.settings.SUPABASE_URL",
        "https://abc.supabase.co",
    )
    with pytest.raises(HTTPException) as exc:
        validate_supabase_storage_url("https://evil.example.com/storage/v1/object/sign/x")
    assert exc.value.status_code == 400


def test_validate_supabase_storage_url_rejects_non_storage_path(monkeypatch):
    monkeypatch.setattr(
        "app.core.auth.settings.SUPABASE_URL",
        "https://abc.supabase.co",
    )
    with pytest.raises(HTTPException) as exc:
        validate_supabase_storage_url("https://abc.supabase.co/rest/v1/profiles")
    assert exc.value.status_code == 400


def test_trusted_conversation_id_accepts_owned_conversation(monkeypatch):
    client = MagicMock()
    query = client.table.return_value.select.return_value
    query.eq.return_value = query
    query.limit.return_value = query
    query.execute.return_value.data = [{"id": "conversation-1"}]
    monkeypatch.setattr("app.api.routes.get_supabase_client", lambda: client)
    assert (
        _trusted_conversation_id("user-1", "conversation-1")
        == "conversation-1"
    )


def test_trusted_conversation_id_rejects_cross_user_conversation(monkeypatch):
    client = MagicMock()
    query = client.table.return_value.select.return_value
    query.eq.return_value = query
    query.limit.return_value = query
    query.execute.return_value.data = []
    monkeypatch.setattr("app.api.routes.get_supabase_client", lambda: client)
    with pytest.raises(HTTPException) as exc:
        _trusted_conversation_id("user-1", "conversation-2")
    assert exc.value.status_code == 403
