import base64

import pytest

from app.core.config import settings
from app.services.connection_secrets import decrypt_json, decrypt_text, encrypt_json, encrypt_text
from app.services.network_security import UnsafeDestinationError, validate_outbound_host


def test_connection_secrets_are_authenticated_ciphertext(monkeypatch):
    key = base64.urlsafe_b64encode(b"k" * 32).decode("ascii")
    monkeypatch.setattr(settings, "CONNECTION_SECRET_KEY", key)
    encrypted = encrypt_text("super-secret")
    assert encrypted.startswith("enc:v1:")
    assert "super-secret" not in encrypted
    assert decrypt_text(encrypted) == "super-secret"
    payload = encrypt_json({"token": "abc"})
    assert decrypt_json(payload) == {"token": "abc"}


def test_ssrf_guard_rejects_private_dns_resolution(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_PRIVATE_CONNECTORS", False)
    monkeypatch.setattr(
        "app.services.network_security.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("169.254.169.254", 443))],
    )
    with pytest.raises(UnsafeDestinationError):
        validate_outbound_host("metadata.example", 443)
