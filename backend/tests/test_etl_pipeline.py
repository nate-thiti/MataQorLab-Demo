import pandas as pd

from app.core.config import settings
from app.services.data_cleaning import clean_dataframe
from app.services.dataset_engine import DatasetHandle
from app.services.etl_pipeline import (
    apply_recipe_dataframe,
    build_cleaning_preview,
    detect_outliers,
    missing_value_recommendations,
    normalize_recipe,
    validate_data_contract,
)


def test_missing_recommendations_require_review_for_critical_roles():
    df = pd.DataFrame({"revenue": [100.0, None, 300.0], "region": ["A", None, "B"]})
    recommendations = missing_value_recommendations(
        df, {"revenue": "sales", "region": "branch"}
    )
    revenue = next(item for item in recommendations if item["column"] == "revenue")
    assert revenue["critical"] is True
    assert revenue["recommended_method"] == "review"


def test_explicit_impute_adds_provenance_flag():
    df = pd.DataFrame({"amount": [10.0, None, 30.0]})
    cleaned, audit = apply_recipe_dataframe(
        df,
        {"imputations": [{"column": "amount", "method": "median", "confirmed": True}]},
    )
    assert cleaned["amount"].tolist() == [10.0, 20.0, 30.0]
    assert cleaned["amount__imputed"].tolist() == [False, True, False]
    assert audit["imputations"][0]["changed"] == 1


def test_critical_impute_without_confirmation_is_skipped():
    df = pd.DataFrame({"amount": [10.0, None, 30.0]})
    cleaned, audit = apply_recipe_dataframe(
        df,
        {"imputations": [{"column": "amount", "method": "median"}]},
        {"amount": "sales"},
    )
    assert cleaned["amount"].isna().sum() == 1
    assert audit["imputations"][0]["skipped"] == "confirmation_required"


def test_outlier_flag_and_safe_transformations():
    df = pd.DataFrame({
        "price": [10.0] * 9 + [1000.0],
        "units": [2.0] * 10,
        "region": ["A"] * 5 + ["B"] * 5,
    })
    candidates = detect_outliers(df)
    assert candidates[0]["column"] == "price"

    cleaned, audit = apply_recipe_dataframe(
        df,
        {
            "outliers": [{"column": "price", "action": "flag"}],
            "transformations": [
                {
                    "type": "derived",
                    "name": "value",
                    "left": "price",
                    "operator": "*",
                    "right": "units",
                },
                {"type": "filter", "column": "region", "operator": "eq", "value": "A"},
            ],
        },
    )
    assert "price__outlier" in cleaned.columns
    assert "value" in cleaned.columns
    assert len(cleaned) == 5
    assert all(item["status"] == "applied" for item in audit["transformations"])


def test_clean_dataframe_embeds_recipe_audit_and_preview():
    before = pd.DataFrame({"amount": [10.0, None, 30.0], "empty": [None, None, None]})
    _notes, after = clean_dataframe(
        before,
        cleaning_profile="standard",
        cleaning_recipe={
            "imputations": [{"column": "amount", "method": "median", "confirmed": True}]
        },
    )
    report = after.attrs["cleaning_report"]
    assert report["recipe_audit"]["applied"] is True
    preview = build_cleaning_preview(before, after, report)
    assert preview["columns_before"] == ["amount", "empty"]
    assert "empty" not in preview["columns_after"]


def test_recipe_normalization_limits_mutating_shapes():
    recipe = normalize_recipe({
        "apply": True,
        "rules": {"dedupe": False, "not_boolean": "yes"},
        "imputations": ["bad", {"column": "x", "method": "mode"}],
        "data_contract": {
            "data_owner": " Finance ",
            "period_status": "complete",
            "mapping_confirmed": True,
            "business_context_reviewed": True,
            "unexpected": "discard me",
        },
    })
    assert recipe["rules"] == {"dedupe": False}
    assert recipe["imputations"] == [{"column": "x", "method": "mode"}]
    assert recipe["data_contract"]["data_owner"] == "Finance"
    assert recipe["data_contract"]["period_status"] == "complete"
    assert recipe["data_contract"]["mapping_confirmed"] is True
    assert "unexpected" not in recipe["data_contract"]


def test_data_contract_v2_is_bounded_and_reports_readiness():
    recipe = normalize_recipe({
        "column_mapping": {"order_id": "order_id", "amount": "sales"},
        "data_contract": {
            "data_owner": "Finance",
            "business_purpose": "Daily revenue decisions",
            "row_grain": "One order line",
            "metric_definitions": [{
                "name": "Revenue",
                "source_column": "amount",
                "aggregation": "sum",
                "definition": "Net revenue excluding VAT",
            }],
            "period_status": "complete",
            "mapping_confirmed": True,
            "business_context_reviewed": True,
            "primary_keys": ["order_id"],
            "currency": "thb",
            "column_contracts": {
                "order_id": {"required": True, "unique": True},
                "amount": {"aggregation": "sum", "sensitivity": "none"},
            },
        },
    })

    contract = recipe["data_contract"]
    assert contract["contract_version"] == "2.0"
    assert contract["currency"] == "THB"
    assert contract["metric_definitions"][0]["source_column"] == "amount"
    assert recipe["contract_validation"]["status"] == "ready"


def test_data_contract_validation_rejects_missing_keys_and_invalid_period():
    result = validate_data_contract(
        {
            "primary_keys": ["missing_id"],
            "reporting_start": "2026-02-01",
            "reporting_end": "2026-01-01",
        },
        {"amount": "sales"},
        ["amount"],
    )

    assert result["status"] == "invalid"
    assert {item["code"] for item in result["errors"]} == {
        "primary_keys_missing",
        "invalid_reporting_period",
    }


def test_column_contract_quality_rules_are_executed():
    frame = pd.DataFrame({
        "order_id": ["A", "A", None],
        "status": ["paid", "invalid", "paid"],
    })
    _, audit = apply_recipe_dataframe(
        frame,
        {
            "data_contract": {
                "primary_keys": ["order_id"],
                "column_contracts": {
                    "order_id": {"required": True, "unique": True},
                    "status": {"allowed_values": ["paid", "cancelled"]},
                },
            },
        },
    )

    alert_types = {item["type"] for item in audit["quality_alerts"]}
    assert {
        "required_null",
        "uniqueness",
        "accepted_values",
        "primary_key_null",
        "primary_key_duplicate",
    }.issubset(alert_types)


def test_optional_contract_column_does_not_block_strict_processing():
    _, audit = apply_recipe_dataframe(
        pd.DataFrame({"amount": [10.0]}),
        {
            "data_contract": {
                "column_contracts": {
                    "optional_note": {"required": False},
                    "required_id": {"required": True},
                },
            },
        },
    )

    alerts = {item["column"]: item for item in audit["quality_alerts"]}
    assert alerts["optional_note"]["severity"] == "warning"
    assert alerts["required_id"]["severity"] == "critical"


def test_recipe_runs_on_full_duckdb_handle():
    old = settings.DUCKDB_ROW_THRESHOLD
    settings.DUCKDB_ROW_THRESHOLD = 2
    try:
        handle = DatasetHandle.from_dataframe(
            pd.DataFrame({"amount": [10.0, None, 30.0], "region": ["A", "A", "B"]})
        )
        _notes, cleaned = handle.prepare_for_analysis(
            {"amount": "num", "region": "branch"},
            "conservative",
            {
                "imputations": [
                    {"column": "amount", "method": "median", "confirmed": True}
                ],
                "transformations": [
                    {"type": "filter", "column": "region", "operator": "eq", "value": "A"}
                ],
            },
        )
        result = cleaned.to_pandas()
        assert len(result) == 2
        assert result["amount"].tolist() == [10.0, 20.0]
        assert result["amount__imputed"].tolist() == [False, True]
        assert cleaned._cleaning_report["recipe_audit"]["engine"] == "duckdb"
    finally:
        settings.DUCKDB_ROW_THRESHOLD = old
