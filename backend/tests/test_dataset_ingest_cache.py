"""Tests for dataset ingest disk cache."""
import os

import pandas as pd
import pytest

from app.core.config import settings
from app.services.dataset_engine import DatasetHandle
from app.services.dataset_ingest_cache import (
    persist_ingest_cache,
    try_load_cached_handle,
)


def test_ingest_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATASET_INGEST_CACHE_DIR", str(tmp_path))
    old = settings.DUCKDB_ROW_THRESHOLD
    settings.DUCKDB_ROW_THRESHOLD = 3
    try:
        df = pd.DataFrame({"a": [1, 2, 3, 4]})
        handle = DatasetHandle.from_dataframe(df)
        persist_ingest_cache("user1", "data.csv", 100, handle)
        restored = try_load_cached_handle("user1", "data.csv", 100)
        assert restored is not None
        assert restored.row_count() == 4
        assert restored.is_large
    finally:
        settings.DUCKDB_ROW_THRESHOLD = old


def test_ingest_cache_miss_on_size_change(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATASET_INGEST_CACHE_DIR", str(tmp_path))
    assert try_load_cached_handle("user1", "data.csv", 999) is None


def test_ingest_cache_roundtrip_for_small_unregistered_dataframe(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATASET_INGEST_CACHE_DIR", str(tmp_path))
    old = settings.DUCKDB_ROW_THRESHOLD
    settings.DUCKDB_ROW_THRESHOLD = 1000
    try:
        handle = DatasetHandle.from_dataframe(
            pd.DataFrame({"branch": ["A", "B"], "revenue": [10, 20]})
        )
        assert handle._df is not None

        persist_ingest_cache("user-small", "small.csv", 42, handle)
        restored = try_load_cached_handle("user-small", "small.csv", 42)

        assert restored is not None
        assert restored.row_count() == 2
        assert restored.to_pandas().to_dict("records") == [
            {"branch": "A", "revenue": 10},
            {"branch": "B", "revenue": 20},
        ]
    finally:
        settings.DUCKDB_ROW_THRESHOLD = old


def test_cached_handle_supports_column_mapping(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATASET_INGEST_CACHE_DIR", str(tmp_path))
    old = settings.DUCKDB_ROW_THRESHOLD
    settings.DUCKDB_ROW_THRESHOLD = 2
    try:
        df = pd.DataFrame({"sales": ["10", "20", "30"], "region": ["A", "B", "A"]})
        handle = DatasetHandle.from_dataframe(df)
        persist_ingest_cache("user1", "sales.xlsx", 100, handle)
        restored = try_load_cached_handle("user1", "sales.xlsx", 100)
        assert restored is not None
        notes, mapped = restored.apply_mapping_clean({"sales": "sales", "region": "branch"})
        assert mapped.row_count() == 3
        assert isinstance(notes, list)
    finally:
        settings.DUCKDB_ROW_THRESHOLD = old


def test_cached_handle_supports_prepare_for_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATASET_INGEST_CACHE_DIR", str(tmp_path))
    old = settings.DUCKDB_ROW_THRESHOLD
    settings.DUCKDB_ROW_THRESHOLD = 2
    try:
        df = pd.DataFrame(
                {
                    "sales": ["฿10", "20", "20"],
                    "region": ["North", "North", "North"],
                }
            )
        handle = DatasetHandle.from_dataframe(df)
        persist_ingest_cache("user1", "Sales2025.xlsx", 100, handle)
        restored = try_load_cached_handle("user1", "Sales2025.xlsx", 100)
        assert restored is not None

        notes, prepared = restored.prepare_for_analysis(
            {"sales": "sales", "region": "branch"},
            cleaning_profile="standard",
        )

        assert prepared.row_count() == 2
        assert prepared._cleaning_report.get("profile") == "standard"
        assert isinstance(notes, list)
    finally:
        settings.DUCKDB_ROW_THRESHOLD = old
