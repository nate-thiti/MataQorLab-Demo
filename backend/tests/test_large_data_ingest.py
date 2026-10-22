"""Tests for large-data ingest paths, streaming helpers, and pipeline optimizations."""
import csv
import json
import os
import tempfile

import pandas as pd
import pytest

from app.core.config import settings
from app.services.dataset_engine import DatasetHandle
from app.services.duckdb_extended_analytics import append_extended_duckdb_analytics
from app.services.large_data_ingest import ingest_json_value, records_to_handle
from app.services.sql_execution import effective_row_cap, enforce_row_limit


def test_records_to_handle_small():
    records = [{"a": i, "b": i * 2} for i in range(10)]
    handle = records_to_handle(records)
    assert handle is not None
    assert handle.row_count() == 10
    assert not handle.is_large


def test_records_to_handle_large_uses_duckdb():
    old = settings.DUCKDB_ROW_THRESHOLD
    settings.DUCKDB_ROW_THRESHOLD = 5
    try:
        records = [{"value": i} for i in range(20)]
        handle = records_to_handle(records)
        assert handle is not None
        assert handle.is_large
        assert handle.row_count() == 20
    finally:
        settings.DUCKDB_ROW_THRESHOLD = old


def test_ingest_json_value_nested_array():
    payload = {"data": [{"x": 1, "y": 2}, {"x": 3, "y": 4}]}
    handle = ingest_json_value(payload)
    assert handle is not None
    assert handle.row_count() == 2


def test_ingest_json_bytes_via_dataset_engine():
    records = [{"id": i, "name": f"n{i}"} for i in range(8)]
    raw = json.dumps(records).encode("utf-8")
    handle = DatasetHandle.from_bytes(raw, "export.json")
    assert handle is not None
    assert handle.row_count() == 8


def test_from_file_path_csv_large():
    old = settings.DUCKDB_ROW_THRESHOLD
    settings.DUCKDB_ROW_THRESHOLD = 5
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", newline="") as tmp:
            path = tmp.name
            writer = csv.writer(tmp)
            writer.writerow(["value"])
            for i in range(12):
                writer.writerow([i])
        handle = DatasetHandle.from_file_path(path, "data.csv", cleanup_path=True)
        assert handle is not None
        assert handle.is_large
        assert handle.row_count() == 12
        assert not os.path.exists(path)
    finally:
        settings.DUCKDB_ROW_THRESHOLD = old
        if path and os.path.exists(path):
            os.unlink(path)


def test_summarize_df_cached_once():
    old = settings.DUCKDB_ROW_THRESHOLD
    settings.DUCKDB_ROW_THRESHOLD = 3
    try:
        df = pd.DataFrame({"a": [1, 2, 3, 4], "b": [10, 20, 30, 40]})
        handle = DatasetHandle.from_dataframe(df)
        s1 = handle.summarize_df()
        s2 = handle.summarize_df()
        assert s1 is s2
        handle.profile_columns(s1)
        stats = handle.duckdb_summarize_stats(s1)
        assert "Dataset Overview" in stats[0]
    finally:
        settings.DUCKDB_ROW_THRESHOLD = old


def test_skip_expensive_extended_analytics():
    old_threshold = settings.EXTENDED_ANALYTICS_ROW_THRESHOLD
    old_duck = settings.DUCKDB_ROW_THRESHOLD
    settings.EXTENDED_ANALYTICS_ROW_THRESHOLD = 10
    settings.DUCKDB_ROW_THRESHOLD = 3
    try:
        df = pd.DataFrame(
            {
                "order_date": pd.date_range("2024-01-01", periods=12, freq="MS"),
                "revenue": range(12),
                "region": ["A", "B"] * 6,
            }
        )
        big = pd.concat([df] * 2, ignore_index=True)
        handle = DatasetHandle.from_dataframe(big)
        summary = handle.summarize_df()
        lines = append_extended_duckdb_analytics(
            handle,
            {"order_date": "date", "revenue": "sales", "region": "branch"},
            summary,
        )
        text = "\n".join(lines)
        assert "Skipped categorical/correlation/outlier" in text
        assert "Relationships" not in text
    finally:
        settings.EXTENDED_ANALYTICS_ROW_THRESHOLD = old_threshold
        settings.DUCKDB_ROW_THRESHOLD = old_duck


def test_effective_row_cap_reads_limit():
    sql = "SELECT * FROM t LIMIT 120000"
    assert effective_row_cap(sql) == 120000


def test_enforce_row_limit_clamps_to_max():
    sql = "SELECT * FROM t LIMIT 99999999"
    out = enforce_row_limit(sql, int(settings.MAX_SQL_RESULT_ROWS))
    assert f"LIMIT {settings.MAX_SQL_RESULT_ROWS}" in out
