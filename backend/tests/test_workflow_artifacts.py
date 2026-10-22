"""Recovery behavior for internal workflow artifacts."""
from __future__ import annotations

import pytest

from app.services.workflow.artifacts import load_cleaned_artifact


def test_missing_cleaned_artifact_allows_source_rebuild(monkeypatch):
    def missing(*_args, **_kwargs):
        raise RuntimeError("{'statusCode': 404, 'message': Object not found}")

    monkeypatch.setattr(
        "app.services.workflow.artifacts.load_handle_from_storage", missing
    )

    assert load_cleaned_artifact("user-1", "cleaned.parquet") is None


def test_non_missing_cleaned_artifact_failure_is_not_hidden(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("Storage connection timed out")

    monkeypatch.setattr(
        "app.services.workflow.artifacts.load_handle_from_storage", unavailable
    )

    with pytest.raises(RuntimeError, match="timed out"):
        load_cleaned_artifact("user-1", "cleaned.parquet")
