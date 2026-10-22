"""Tests for standard data cleaning pipeline."""
import json
import math

import pandas as pd

from app.core.json_safety import json_safe_dumps
from app.core.config import settings
from app.services.data_cleaning import clean_dataframe, strip_currency_text
from app.services.dataset_engine import DatasetHandle


def test_strip_currency_text():
    assert strip_currency_text("฿1,234.50") == "1234.50"
    assert strip_currency_text("$ 2,000") == "2000"
    assert strip_currency_text(42) == 42


def test_clean_dataframe_trims_and_dedupes():
    df = pd.DataFrame(
        {
            " sales ": [" 100 ", "200", " 100 "],
            "region": ["A", "B", "A"],
        }
    )
    notes, cleaned = clean_dataframe(df)
    assert len(cleaned) == 2
    assert "sales" in cleaned.columns
    assert any("duplicate" in n.lower() for n in notes)
    report = cleaned.attrs["cleaning_report"]
    assert report["profile"] == "standard"
    assert report["engine"] == "pandas"
    assert report["dropped_duplicates"] == 1
    assert report["quality_score"] < 100
    assert report["schema_profile"]["sales"]["inferred_type"] == "numeric"
    assert report["preview"]["before"][0]["sales"] == " 100 "
    assert report["preview"]["after"][0]["sales"] == "100"
    assert report["lineage"]["transform"] == "transform-on-analyze"


def test_cleaning_preview_outputs_strict_json_for_nan_values():
    df = pd.DataFrame({"discount": [float("nan"), "10%"], "amount": [math.inf, 25]})

    _notes, cleaned = clean_dataframe(df, cleaning_profile="conservative")
    report = cleaned.attrs["cleaning_report"]
    payload = json_safe_dumps(report, ensure_ascii=False)

    assert "NaN" not in payload
    assert "Infinity" not in payload
    assert json.loads(payload)["preview"]["before"][0]["discount"] is None


def test_clean_dataframe_conservative_profile_keeps_duplicates_and_merged_gaps():
    df = pd.DataFrame(
        {
            "dept": ["Sales", None, None, "Sales"],
            "amount": [10, 20, 30, 10],
        }
    )
    notes, cleaned = clean_dataframe(df, {"amount": "sales"}, cleaning_profile="conservative")
    report = cleaned.attrs["cleaning_report"]
    assert len(cleaned) == 4
    assert cleaned["dept"].isna().sum() == 2
    assert report["profile"] == "conservative"
    assert report["dropped_duplicates"] == 0
    assert report["forward_filled_columns"] == []
    assert not any("duplicate" in n.lower() for n in notes)


def test_clean_dataframe_merged_cells():
    df = pd.DataFrame(
        {
            "dept": ["Sales", None, None, "HR", None],
            "amount": [10, 20, 30, 40, 50],
        }
    )
    notes, cleaned = clean_dataframe(df)
    assert cleaned["dept"].tolist() == ["Sales", "Sales", "Sales", "HR", "HR"]
    assert any("merged" in n.lower() for n in notes)


def test_clean_dataframe_currency_numeric_mapping():
    df = pd.DataFrame({"price": ["฿1,000", "$2,500", "bad"]})
    notes, _cleaned = clean_dataframe(df, {"price": "sales"})
    assert any("non-numeric" in n for n in notes)


def test_clean_dataframe_date_mapping():
    df = pd.DataFrame({"when": ["2024-01-01", "not-a-date", "2024-02-01"]})
    notes, cleaned = clean_dataframe(df, {"when": "date"})
    assert pd.api.types.is_datetime64_any_dtype(cleaned["when"])
    assert any("could not be parsed as dates" in n for n in notes)


def test_prepare_for_analysis_combined():
    df = pd.DataFrame({"sales": ["฿10", "20", "x"], "note": ["a", "b", "c"]})
    handle = DatasetHandle.from_dataframe(df)
    notes, prepared = handle.prepare_for_analysis({"sales": "sales", "note": "category"})
    assert prepared.row_count() == 3
    assert notes


def test_standard_clean_duckdb_large(tmp_path):
    old = settings.DUCKDB_ROW_THRESHOLD
    settings.DUCKDB_ROW_THRESHOLD = 2
    try:
        path = tmp_path / "data.csv"
        path.write_text("region,amount\nNorth,$100\n,$200\nNorth,$100\nSouth,$300\n", encoding="utf-8")
        handle = DatasetHandle.from_file_path(str(path), "data.csv")
        assert handle is not None and handle.is_large
        notes, cleaned = handle.prepare_for_analysis({"amount": "sales", "region": "branch"})
        assert cleaned.row_count() <= 4
        assert notes
    finally:
        settings.DUCKDB_ROW_THRESHOLD = old


def test_standard_clean_duckdb_drops_empty_rows_and_columns(tmp_path):
    old = settings.DUCKDB_ROW_THRESHOLD
    settings.DUCKDB_ROW_THRESHOLD = 2
    try:
        path = tmp_path / "empty_rows_cols.csv"
        path.write_text(
            "region,amount,empty_col\nNorth,100,\n,,\nSouth,200,\n",
            encoding="utf-8",
        )
        handle = DatasetHandle.from_file_path(str(path), "empty_rows_cols.csv")
        assert handle is not None and handle.is_large

        notes, cleaned = handle.prepare_for_analysis({"amount": "sales", "region": "branch"})

        assert cleaned.row_count() == 2
        assert "empty_col" not in cleaned.column_names()
        report = cleaned._cleaning_report
        assert report["engine"] == "duckdb"
        assert report["dropped_empty_rows"] == 1
        assert report["dropped_columns"] == ["empty_col"]
        assert report["quality_score"] < 100
        assert report["schema_profile"]["amount"]["semantic_role"] == "sales"
        assert report["preview"]["before"][0]["empty_col"] is None
        assert report["preview"]["after"][0]["region"] == "North"
        assert any("all-empty column" in n for n in notes)
        assert any("empty row" in n for n in notes)
    finally:
        settings.DUCKDB_ROW_THRESHOLD = old


def test_csv_ingest_detects_real_header_after_intro_rows(tmp_path):
    path = tmp_path / "messy_header.csv"
    path.write_text(
        "Sales export,,\nGenerated by POS,,\nregion,amount,date\nNorth,100,2026-01-01\nSouth,200,2026-01-02\n",
        encoding="utf-8",
    )

    handle = DatasetHandle.from_file_path(str(path), "messy_header.csv")

    assert handle is not None
    assert handle.column_names() == ["region", "amount", "date"]
    assert handle.row_count() == 2


def test_financial_profile_drops_empty_but_keeps_duplicates():
    df = pd.DataFrame(
        {
            "amount": [100, 100, None],
            "region": ["North", "North", None],
            "empty_col": [None, None, None],
        }
    )
    _notes, cleaned = clean_dataframe(df, {"amount": "sales"}, cleaning_profile="financial")
    report = cleaned.attrs["cleaning_report"]
    assert report["profile"] == "financial"
    assert len(cleaned) == 2
    assert "empty_col" not in cleaned.columns
    assert report["dropped_duplicates"] == 0
    assert report["dropped_columns"] == ["empty_col"]


def test_conservative_profile_skips_structural_and_coercion():
    df = pd.DataFrame(
        {
            "price": ["฿1,000", "bad"],
            "empty_col": [None, None],
            "dept": ["Sales", None],
        }
    )
    _notes, cleaned = clean_dataframe(df, {"price": "sales"}, cleaning_profile="conservative")
    report = cleaned.attrs["cleaning_report"]
    assert report["profile"] == "conservative"
    assert "empty_col" in cleaned.columns
    assert cleaned["price"].tolist() == ["฿1,000", "bad"]
    assert cleaned["dept"].isna().sum() == 1
    assert report["coerced_numeric"] == {}
    assert report["forward_filled_columns"] == []


def test_aggressive_profile_drops_mostly_empty_rows():
    df = pd.DataFrame(
        {
            "region": ["North", None, "South"],
            "amount": [100, None, 200],
            "note": [None, None, None],
            "extra": [None, None, None],
            "flag": [None, None, None],
        }
    )
    _notes, cleaned = clean_dataframe(df, cleaning_profile="aggressive")
    report = cleaned.attrs["cleaning_report"]
    assert report["profile"] == "aggressive"
    assert len(cleaned) == 2
    assert report.get("dropped_mostly_empty_rows", 0) >= 1
