from types import SimpleNamespace

import pytest

from scripts.staging_smoke import _assert_denied, _assert_encrypted


@pytest.mark.parametrize("status_code", [401, 403, 404])
def test_browser_connector_access_must_be_denied(status_code):
    _assert_denied(SimpleNamespace(status_code=status_code), "api_connections")


def test_successful_browser_connector_access_fails_gate():
    with pytest.raises(RuntimeError, match="unavailable to browser roles"):
        _assert_denied(SimpleNamespace(status_code=200), "api_connections")


def test_legacy_plaintext_secret_fails_gate():
    _assert_encrypted("enc:v1:ciphertext", "database_connections/1")
    with pytest.raises(RuntimeError, match="legacy plaintext secret"):
        _assert_encrypted("plaintext", "database_connections/1")
