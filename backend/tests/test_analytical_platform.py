import json
from pathlib import Path

import pandas as pd
import pytest

from app.services.analysis_audit import build_analysis_audit
from app.services.analytical_extensions import (
    assess_join_cardinality,
    forecast_metric,
    infer_grain_and_join_risks,
    parse_and_run_scenario,
)
from app.services.dataset_engine import DatasetHandle
from app.services.domain_analytics import infer_semantic_roles
from app.services.semantic_metrics import execute_semantic_metrics, validate_custom_metric


def _global_sales():
    rows = []
    for month, date in enumerate(pd.date_range("2024-01-01", periods=12, freq="MS")):
        for country in ("US", "DE"):
            rows.append(
                {
                    "order_date": date,
                    "order_id": f"{month}-{country}",
                    "customer_id": f"c-{month % 4}",
                    "country": country,
                    "revenue": 100 + month,
                    "cost": 60 + month,
                }
            )
    return pd.DataFrame(rows)


def test_semantic_metric_layer_uses_one_reusable_definition():
    frame = _global_sales()
    roles = infer_semantic_roles(frame, {})
    results = execute_semantic_metrics(DatasetHandle.from_dataframe(frame), roles, limit=12)
    by_key = {item["definition"]["key"]: item for item in results if "value" in item}

    assert by_key["revenue"]["value"] == pytest.approx(frame["revenue"].sum())
    assert by_key["orders"]["value"] == frame["order_id"].nunique()
    assert "COUNT(DISTINCT" in by_key["orders"]["formula"]
    assert by_key["gross_margin"]["definition"]["version"] == 1


def test_custom_metric_validation_rejects_free_form_sql():
    with pytest.raises(ValueError):
        validate_custom_metric(
            {"key": "unsafe", "aggregation": "select * from secrets", "role": "sales"}
        )


def test_grain_and_many_to_many_join_guard():
    lines = pd.DataFrame(
        {
            "order_id": ["a", "a", "b", "b"],
            "line_id": [1, 2, 1, 2],
            "revenue": [1, 2, 3, 4],
        }
    )
    grain = infer_grain_and_join_risks(
        DatasetHandle.from_dataframe(lines),
        {"order_id": "order_id", "line_id": "line_id"},
    )
    join = assess_join_cardinality(
        pd.DataFrame({"key": [1, 1]}),
        pd.DataFrame({"key": [1, 1, 1]}),
        "key",
    )

    assert grain["grain"] == "order_line"
    assert grain["join_risks"]
    assert join["cardinality"] == "many_to_many"
    assert join["safe"] is False
    assert join["row_multiplier"] == 2


def test_forecast_has_interval_and_does_not_claim_causality():
    frame = _global_sales()
    roles = infer_semantic_roles(frame, {})

    result = forecast_metric(DatasetHandle.from_dataframe(frame), roles)

    assert result["eligible"] is True
    assert len(result["forecast"]) == 3
    assert result["forecast"][0]["lower_95"] <= result["forecast"][0]["value"]
    assert "assumes" in result["caveat"]


def test_scenario_understands_increase_and_decrease():
    result = parse_and_run_scenario(
        "What if price increases 5% and volume decreases 3%?",
        {"revenue": 1000, "cost": 600},
    )

    assert result["assumptions"] == {"price": 5, "volume": -3}
    assert result["projected_revenue"] == pytest.approx(1018.5)
    assert result["projected_profit"] == pytest.approx(418.5)


def test_audit_packet_has_stable_id_and_governance_sections():
    finding = {
        "id": "f_test",
        "metric": "revenue",
        "value": 10,
        "provenance": {"result_hash": "abc"},
    }
    kwargs = {
        "findings": [finding],
        "question_plan": {"steps": []},
        "eligibility": {"forecast": {"eligible": True}},
        "column_intelligence": {"columns": []},
        "grain_intelligence": {"grain": "order"},
        "compute_depth": "deep",
        "data_contract": {
            "data_owner": "Finance",
            "business_purpose": "Daily sales review",
            "row_grain": "One row per order",
            "metric_definition": "Revenue excluding VAT",
            "cancellation_policy": "Exclude cancelled orders",
            "period_status": "complete",
            "mapping_confirmed": True,
            "business_context_reviewed": True,
        },
    }

    first = build_analysis_audit(**kwargs)
    second = build_analysis_audit(**kwargs)

    assert first["audit_id"] == second["audit_id"]
    assert first["contract_version"] == "2.0"
    assert first["grain_intelligence"]["grain"] == "order"
    assert first["verification_layers"]["computation"]["status"] == "verified"
    assert first["verification_layers"]["data_readiness"]["status"] == "verified"
    assert first["verification_layers"]["business_context"]["status"] == "verified"


def test_audit_marks_missing_business_contract_for_review():
    audit = build_analysis_audit(
        findings=[{
            "id": "f_test",
            "provenance": {"result_hash": "abc"},
        }],
        question_plan={"steps": []},
        eligibility={},
        column_intelligence={},
        grain_intelligence={},
        compute_depth="fast",
    )

    assert audit["verification_layers"]["computation"]["status"] == "verified"
    assert audit["verification_layers"]["data_readiness"]["status"] == "needs_review"
    assert audit["verification_layers"]["business_context"]["status"] == "needs_review"


def test_benchmark_corpus_contains_twenty_global_cases():
    path = Path(__file__).parents[1] / "benchmarks/cases/global_analysis.json"
    cases = json.loads(path.read_text(encoding="utf-8"))

    assert len(cases) == 20
    assert len({case["domain"] for case in cases}) >= 8
    assert {"fast", "deep"} == {case["mode"] for case in cases}
