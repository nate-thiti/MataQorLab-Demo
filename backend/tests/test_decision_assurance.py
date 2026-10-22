import numpy as np
import pandas as pd

from app.services.dataset_engine import DatasetHandle
from app.services.decision_assurance import (
    build_causal_eligibility,
    build_decision_assurance_packet,
    build_external_event_timeline,
    run_causal_analyses,
)


def _finding(period="2025-01-01"):
    return {
        "id": "f_sales",
        "type": "change_point",
        "metric": "Revenue",
        "value": 120.0,
        "evidence": "Revenue changed at the detected boundary.",
        "interpretation": "A descriptive change was detected.",
        "provenance": {
            "result_hash": "result123",
            "query_hash": "query123",
            "engine": "test",
            "row_count": 30,
            "period": period,
            "source_columns": ["date", "revenue"],
        },
        "audit": {"formula": "SUM(revenue)"},
    }


def test_packet_builds_all_assurance_layers_and_fails_closed():
    frame = pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=10, freq="MS"),
        "revenue": np.arange(10, dtype=float),
    })
    packet = build_decision_assurance_packet(
        DatasetHandle.from_dataframe(frame),
        findings=[_finding()],
        analytics_results={"detected_roles": {"date": "date", "revenue": "revenue"}},
        data_contract={"mapping_confirmed": True},
    )

    assert packet["claim_graph"]["claim_count"] == 1
    assert packet["confidence_matrix"]["score_meaning"].endswith("not truth probability.")
    assert packet["evidence_requests"]
    assert packet["event_timeline"]["events"]
    assert packet["causal_eligibility"]["status"] == "needs_input"
    assert packet["causal_results"]["blocked"] is True


def test_timeline_does_not_turn_temporal_alignment_into_causality():
    timeline = build_external_event_timeline(
        [_finding("2025-02-10")],
        web_sources=[{
            "title": "Official policy announcement",
            "url": "https://example.gov/policy",
            "published_at": "2025-02-08",
        }],
    )

    assert timeline["alignments"][0]["relation"] == "coincident"
    assert timeline["alignments"][0]["causal_interpretation"] is False


def test_interrupted_time_series_runs_only_after_gate_passes():
    dates = pd.date_range("2023-01-01", periods=24, freq="MS")
    values = np.arange(24, dtype=float) + np.where(np.arange(24) >= 14, 20, 0)
    handle = DatasetHandle.from_dataframe(pd.DataFrame({"date": dates, "revenue": values}))
    contract = {
        "causal_design": {
            "date_column": "date",
            "outcome_column": "revenue",
            "intervention_date": "2024-03-01",
        }
    }
    gate = build_causal_eligibility(handle, data_contract=contract)
    results = run_causal_analyses(handle, gate)

    assert gate["methods"]["interrupted_time_series"]["status"] == "eligible"
    assert results["results"]["interrupted_time_series"]["level_change"] > 15


def test_difference_in_differences_returns_expected_estimate():
    dates = pd.date_range("2024-01-01", periods=10, freq="MS")
    rows = []
    intervention = pd.Timestamp("2024-06-01")
    for date in dates:
        for treated, group in [(0, "control"), (1, "treated")]:
            baseline = 10 + date.month
            outcome = baseline + (5 if treated and date >= intervention else 0)
            rows.append({
                "date": date,
                "outcome": outcome,
                "treated": treated,
                "group": group,
            })
    handle = DatasetHandle.from_dataframe(pd.DataFrame(rows))
    contract = {
        "causal_design": {
            "date_column": "date",
            "outcome_column": "outcome",
            "intervention_date": "2024-06-01",
            "treatment_column": "treated",
            "treatment_value": "1",
            "control_value": "0",
            "group_column": "group",
        }
    }
    gate = build_causal_eligibility(handle, data_contract=contract)
    results = run_causal_analyses(handle, gate)

    assert gate["methods"]["difference_in_differences"]["status"] == "eligible"
    assert abs(results["results"]["difference_in_differences"]["estimate"] - 5) < 1e-9


def test_counterfactual_reports_predictive_gap():
    dates = pd.date_range("2022-01-01", periods=30, freq="MS")
    predictor = np.arange(30, dtype=float)
    outcome = 2 * predictor + 3
    outcome[24:] += 7
    handle = DatasetHandle.from_dataframe(pd.DataFrame({
        "date": dates,
        "outcome": outcome,
        "control": predictor,
    }))
    contract = {
        "causal_design": {
            "date_column": "date",
            "outcome_column": "outcome",
            "intervention_date": "2024-01-01",
            "predictor_columns": ["control"],
        }
    }
    gate = build_causal_eligibility(handle, data_contract=contract)
    results = run_causal_analyses(handle, gate)

    assert gate["methods"]["counterfactual"]["status"] == "eligible"
    assert abs(results["results"]["counterfactual"]["average_gap"] - 7) < 1e-8
