"""Tests for DuckDB extended analytics, SQL limits, and unified analytics service."""
import pandas as pd
import pytest

from app.core.config import settings
from app.services.dataset_engine import DatasetHandle
from app.services.duckdb_extended_analytics import append_extended_duckdb_analytics
from app.services.sql_execution import enforce_row_limit, validate_select_sql
from app.services.analytics_service import calculate_analytics_for_handle


@pytest.fixture
def sales_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "order_date": pd.date_range("2024-01-01", periods=12, freq="MS"),
            "revenue": [100, 120, 110, 130, 125, 140, 135, 150, 145, 160, 155, 170],
            "region": ["A", "B"] * 6,
            "cost": [60, 70, 65, 75, 72, 80, 78, 85, 82, 90, 88, 95],
        }
    )


def test_enforce_row_limit_appends():
    sql = "SELECT * FROM t"
    assert "LIMIT 100" in enforce_row_limit(sql, 100)


def test_enforce_row_limit_clamps_high():
    sql = "SELECT * FROM t LIMIT 999999"
    out = enforce_row_limit(sql, 50000)
    assert "LIMIT 50000" in out


def test_validate_select_rejects_delete():
    ok, _ = validate_select_sql("DELETE FROM users")
    assert not ok


def test_extended_duckdb_analytics_on_large_handle(sales_df):
    old = settings.DUCKDB_ROW_THRESHOLD
    settings.DUCKDB_ROW_THRESHOLD = 3
    try:
        big = pd.concat([sales_df] * 3, ignore_index=True)
        handle = DatasetHandle.from_dataframe(big)
        assert handle.is_large
        mapping = {"order_date": "date", "revenue": "sales", "cost": "cost", "region": "branch"}
        roles = handle.infer_roles_from_sample(mapping)
        lines = append_extended_duckdb_analytics(handle, roles)
        text = "\n".join(lines)
        assert "Time-Series" in text or "Categorical" in text or "Relationships" in text
    finally:
        settings.DUCKDB_ROW_THRESHOLD = old


def test_calculate_analytics_for_handle_large(sales_df):
    old = settings.DUCKDB_ROW_THRESHOLD
    settings.DUCKDB_ROW_THRESHOLD = 5
    try:
        big = pd.concat([sales_df] * 2, ignore_index=True)
        handle = DatasetHandle.from_dataframe(big)

        def fake_pandas(_df, _map):
            return {"formatted_notes": "pandas", "raw_metrics": []}

        result = calculate_analytics_for_handle(
            handle,
            {"revenue": "sales", "order_date": "date"},
            pandas_calculator=fake_pandas,
        )
        assert result.get("is_large") is True
        assert "DuckDB" in result.get("formatted_notes", "")
    finally:
        settings.DUCKDB_ROW_THRESHOLD = old


def test_calculate_analytics_for_handle_prepares_unprepared_small_handle():
    df = pd.DataFrame({"sales": ["฿10", "bad"], "empty": [None, None]})
    handle = DatasetHandle.from_dataframe(df)

    result = calculate_analytics_for_handle(
        handle,
        {"sales": "sales"},
        pandas_calculator=lambda cleaned, _mapping: {
            "formatted_notes": f"cols={list(cleaned.columns)} sales={cleaned['sales'].tolist()}",
            "raw_metrics": [],
        },
    )

    assert "Data Validation Notes" in result["formatted_notes"]
    assert "cols=['sales']" in result["formatted_notes"]
    assert result["cleaning_report"]["dropped_columns"] == ["empty"]
    assert result["data_quality_score"] < 100
    assert result["schema_profile"]["sales"]["semantic_role"] == "sales"
    assert result["lineage"]["transform"] == "transform-on-analyze"


def test_dataset_handle_for_sql_execution(sales_df):
    handle = DatasetHandle.from_dataframe(sales_df)
    exec_handle = DatasetHandle.for_sql_execution(handle)
    out = exec_handle.execute_select(
        "SELECT region, SUM(CAST(revenue AS DOUBLE)) AS s FROM df GROUP BY 1 ORDER BY s DESC"
    )
    assert len(out) >= 1
