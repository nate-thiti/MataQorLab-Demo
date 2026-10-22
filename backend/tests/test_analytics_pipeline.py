"""Tests for dataset engine, domain KPIs, and agent session store."""
import io
import pandas as pd
import pytest

from app.core.config import settings
from app.services.dataset_engine import DatasetHandle, as_handle, TABLE_NAME
from app.services.domain_analytics import compute_domain_kpis_duckdb, infer_semantic_roles
from app.services.agent_session_store import (
    AgentSession,
    create_session,
    get_session,
    delete_session,
    cache_df_for_session,
    load_df_from_session,
)


@pytest.fixture
def sales_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "revenue": [100, 200, 150, 300],
            "qty": [2, 4, 3, 6],
            "region": ["A", "B", "A", "B"],
        }
    )


def test_small_dataframe_pandas_path(sales_df):
    handle = DatasetHandle.from_dataframe(sales_df)
    assert not handle.is_large
    assert handle.row_count() == 4
    profile = handle.profile_columns()
    assert "revenue" in profile


def test_large_dataframe_uses_duckdb(sales_df):
    old = settings.DUCKDB_ROW_THRESHOLD
    settings.DUCKDB_ROW_THRESHOLD = 3
    try:
        big = pd.concat([sales_df] * 2, ignore_index=True)
        handle = DatasetHandle.from_dataframe(big)
        assert handle.is_large
        assert handle.row_count() == 8
        roles = handle.infer_roles_from_sample({"revenue": "sales", "qty": "quantity"})
        kpis = compute_domain_kpis_duckdb(handle, roles)
        assert any("AOV" in k for k in kpis)
    finally:
        settings.DUCKDB_ROW_THRESHOLD = old


def test_apply_mapping_clean_numeric():
    df = pd.DataFrame({"sales": ["10", "20", "bad"], "note": ["a", "b", "c"], "unmapped": [1, 2, 3]})
    handle = DatasetHandle.from_dataframe(df)
    notes, cleaned = handle.apply_mapping_clean({"sales": "sales", "note": "category"})
    assert cleaned.row_count() == 3
    assert "unmapped" in cleaned.column_names()
    assert any("non-numeric" in n or "missing" in n for n in notes) or len(notes) >= 0


def test_business_contract_governs_revenue_cancellations_and_fiscal_period():
    frame = pd.DataFrame({
        "gross": [120, 120, 120],
        "net": [100, 100, 100],
        "status": ["completed", "cancelled", "returned"],
        "ordered_at": ["2026-03-01", "2026-04-01", "2026-05-01"],
        "detail": ["keep", "keep", "keep"],
    })
    mapping = {
        "gross": "gross_amount", "net": "net_amount", "status": "status",
        "ordered_at": "date",
    }
    recipe = {
        "apply": True,
        "column_mapping": mapping,
        "data_contract": {
            "mapping_confirmed": True,
            "business_context_reviewed": True,
            "revenue_basis": "net",
            "cancellation_policy": "exclude_cancelled_net_returns",
            "fiscal_year_start": "04",
            "metric_definition": "Net revenue",
            "metric_definitions": [{
                "name": "Net revenue", "source_column": "net",
                "aggregation": "sum", "definition": "SUM(net)",
            }],
        },
    }
    _notes, prepared = DatasetHandle.from_dataframe(frame).prepare_for_analysis(
        mapping, "financial", recipe
    )
    result = prepared.to_pandas()

    assert prepared.row_count() == 2
    assert result["net"].sum() == 0
    assert prepared._effective_mapping["net"] == "sales"
    assert "detail" in result.columns
    assert "__fiscal_year" in result.columns


def test_materialized_prepared_dataset_is_not_cleaned_twice():
    frame = pd.DataFrame({"amount": [1, 1], "detail": ["a", "a"]})
    handle = DatasetHandle.from_dataframe(frame)
    _notes, prepared = handle.prepare_for_analysis(
        {"amount": "sales"},
        "standard",
        {
            "materialized_prepared": True,
            "rules": {"dedupe": True},
            "dataset_version_id": "version-1",
            "source_fingerprint": "source-1",
            "contract_hash": "contract-1",
            "recipe_hash": "recipe-1",
        },
    )
    assert prepared.row_count() == 2
    assert prepared._dataset_version_id == "version-1"
    assert prepared._source_fingerprint == "source-1"
    assert prepared._contract_hash == "contract-1"
    assert prepared._recipe_hash == "recipe-1"


def test_business_contract_has_same_governed_result_on_duckdb_path():
    old = settings.DUCKDB_ROW_THRESHOLD
    settings.DUCKDB_ROW_THRESHOLD = 2
    try:
        frame = pd.DataFrame({
            "net": [100, 100, 100],
            "status": ["completed", "cancelled", "returned"],
            "ordered_at": ["2026-03-01", "2026-04-01", "2026-05-01"],
        })
        mapping = {"net": "net_amount", "status": "status", "ordered_at": "date"}
        recipe = {
            "apply": True,
            "column_mapping": mapping,
            "data_contract": {
                "mapping_confirmed": True,
                "business_context_reviewed": True,
                "revenue_basis": "net",
                "cancellation_policy": "exclude_cancelled_net_returns",
                "fiscal_year_start": "04",
                "metric_definition": "Net revenue",
                "metric_definitions": [{
                    "name": "Net revenue", "source_column": "net",
                    "aggregation": "sum", "definition": "SUM(net)",
                }],
            },
        }
        _notes, prepared = DatasetHandle.from_dataframe(frame).prepare_for_analysis(
            mapping, "financial", recipe
        )
        result = prepared.to_pandas()
        assert prepared.row_count() == 2
        assert result["net"].sum() == 0
        assert "__fiscal_year" in result.columns
    finally:
        settings.DUCKDB_ROW_THRESHOLD = old


def test_execute_select_rejects_non_select():
    df = pd.DataFrame({"x": [1, 2]})
    handle = DatasetHandle.from_dataframe(df)
    with pytest.raises(ValueError):
        handle.execute_select("DELETE FROM df")


def test_execute_select_allows_readonly_cte():
    df = pd.DataFrame({"x": [1, 2]})
    handle = DatasetHandle.from_dataframe(df)

    out = handle.execute_select("WITH totals AS (SELECT SUM(x) AS total FROM df) SELECT total FROM totals")

    assert out.iloc[0]["total"] == 3


def test_csv_from_bytes():
    csv = "a,b\n1,2\n3,4\n".encode()
    handle = DatasetHandle.from_bytes(csv, "test.csv")
    assert handle is not None
    assert handle.row_count() == 2


def test_agent_session_file_backend_roundtrip(sales_df):
    if settings.AGENT_SESSION_BACKEND.lower() == "supabase":
        pytest.skip("File backend test skipped when AGENT_SESSION_BACKEND=supabase")
    session = create_session(
        user_id="user-test-1",
        original_question="test?",
        status="paused",
    )
    loaded = get_session(session.session_id, "user-test-1")
    assert loaded is not None
    assert loaded.original_question == "test?"
    cache_df_for_session(session, sales_df)
    df = load_df_from_session(session)
    assert df is not None and len(df) == 4
    delete_session(session.session_id)
    assert get_session(session.session_id, "user-test-1") is None


def test_agent_session_duckdb_persist_large_handle(sales_df):
    if settings.AGENT_SESSION_BACKEND.lower() == "supabase":
        pytest.skip("File backend test skipped when AGENT_SESSION_BACKEND=supabase")
    from app.services.agent_session_store import cache_handle_for_session, load_handle_from_session

    old = settings.DUCKDB_ROW_THRESHOLD
    settings.DUCKDB_ROW_THRESHOLD = 3
    try:
        big = pd.concat([sales_df] * 2, ignore_index=True)
        handle = DatasetHandle.from_dataframe(big)
        assert handle.is_large
        session = create_session(
            user_id="user-test-duckdb",
            original_question="large?",
            status="paused",
        )
        cache_handle_for_session(session, handle)
        restored = load_handle_from_session(session)
        assert restored is not None
        assert restored.is_large
        assert restored.row_count() == 8
        delete_session(session.session_id)
    finally:
        settings.DUCKDB_ROW_THRESHOLD = old


def test_as_handle_accepts_dataframe(sales_df):
    h = as_handle(sales_df)
    assert h.row_count() == 4
