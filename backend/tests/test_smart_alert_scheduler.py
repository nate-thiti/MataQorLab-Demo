from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.services.smart_alert_scheduler import (
    SmartAlertError,
    claim_due_alert_rules,
    dispatch_alert,
    evaluate_condition,
    extract_metric_value,
    run_claimed_alert_rule,
)


def test_extract_metric_value_resolves_exact_dashboard_kpi():
    value, metric = extract_metric_value(
        {
            "kpis": [
                {"kind": "count", "field": None, "label": "Rows", "value": 12},
                {
                    "kind": "sum",
                    "field": "Revenue",
                    "label": "Total revenue",
                    "value": 1250.5,
                },
            ]
        },
        "Revenue",
    )

    assert value == 1250.5
    assert metric["label"] == "Total revenue"


def test_extract_metric_value_fails_closed_instead_of_guessing():
    with pytest.raises(SmartAlertError, match="Available KPIs"):
        extract_metric_value(
            {"kpis": [{"kind": "sum", "field": "Sales", "label": "Sales", "value": 5}]},
            "Revenue",
        )


@pytest.mark.parametrize(
    ("operator", "current", "threshold", "previous", "matched", "comparison"),
    [
        ("gt", 11, 10, None, True, 11),
        ("lte", 10, 10, None, True, 10),
        ("change_gt", 120, 10, 100, True, 20),
        ("change_gt", 105, 10, 100, False, 5),
        ("change_lt", 80, 10, 100, True, -20),
    ],
)
def test_evaluate_condition_is_deterministic(
    operator,
    current,
    threshold,
    previous,
    matched,
    comparison,
):
    result, compared, _reason = evaluate_condition(
        operator,
        current,
        threshold,
        previous,
    )

    assert result is matched
    assert compared == pytest.approx(comparison)


def test_change_alert_records_a_baseline_before_triggering():
    matched, compared, reason = evaluate_condition("change_gt", 100, 10, None)

    assert matched is False
    assert compared is None
    assert reason == "baseline_recorded"


def test_claim_due_alerts_uses_bounded_worker_settings():
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = [{"id": "rule-1"}]

    result = claim_due_alert_rules(client, "worker-1")

    assert result == [{"id": "rule-1"}]
    client.rpc.assert_called_once_with(
        "claim_due_customer_alert_rules",
        {
            "p_worker_id": "worker-1",
            "p_limit": settings.SMART_ALERT_BATCH_SIZE,
            "p_lease_seconds": settings.SMART_ALERT_LEASE_SECONDS,
        },
    )


def test_in_app_delivery_needs_no_external_credentials():
    results, errors = dispatch_alert(
        {
            "id": "rule-1",
            "name": "Revenue alert",
            "report_id": "report-1",
            "metric_key": "Revenue",
            "operator": "gt",
            "threshold": 10,
            "channels": ["in_app"],
        },
        current_value=12,
        comparison_value=12,
    )

    assert errors == []
    assert results == {"in_app": {"status": "delivered"}}


def test_email_delivery_fails_with_auditable_reason_without_recipient():
    _results, errors = dispatch_alert(
        {
            "id": "rule-1",
            "name": "Revenue alert",
            "report_id": "report-1",
            "metric_key": "Revenue",
            "operator": "gt",
            "threshold": 10,
            "channels": ["email"],
            "recipients": [],
        },
        current_value=12,
        comparison_value=12,
    )

    assert errors == ["email: no recipient configured"]


def test_smart_alert_migration_has_atomic_leases_and_idempotency():
    sql = (
        Path(__file__).parents[1] / "supabase" / "smart_alert_evaluator.sql"
    ).read_text(encoding="utf-8")

    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "idx_customer_alert_rules_due" in sql
    assert "idx_customer_alert_events_evaluation_key" in sql
    assert "evaluation_interval_minutes BETWEEN 1 AND 1440" in sql
    assert "FROM PUBLIC, anon, authenticated" in sql
    assert "TO service_role" in sql


def test_run_claimed_alert_persists_event_before_delivery(monkeypatch):
    client = MagicMock()
    query = MagicMock()
    client.table.return_value = query
    for method in ("select", "eq", "limit", "insert", "update"):
        getattr(query, method).return_value = query
    query.execute.side_effect = [
        MagicMock(data=[]),
        MagicMock(data=[{"id": "event-1"}]),
        MagicMock(data=[]),
        MagicMock(data=[]),
    ]
    monkeypatch.setattr(
        "app.services.smart_alert_scheduler._evaluate_metric",
        lambda _client, _rule: (
            120.0,
            {"kind": "sum", "field": "Revenue", "label": "Revenue", "value": 120},
            {"row_count": 10, "aggregation_scope": "full_dataset"},
        ),
    )
    monkeypatch.setattr(
        "app.services.smart_alert_scheduler.dispatch_alert",
        lambda _rule, **_values: ({"in_app": {"status": "delivered"}}, []),
    )

    result = run_claimed_alert_rule(
        {
            "id": "rule-1",
            "user_id": "user-1",
            "report_id": "report-1",
            "name": "Revenue alert",
            "metric_key": "Revenue",
            "operator": "gt",
            "threshold": 100,
            "channels": ["in_app"],
            "evaluation_interval_minutes": 5,
            "next_evaluation_at": "2026-07-29T00:00:00+00:00",
            "consecutive_failures": 0,
        },
        "worker-1",
        client=client,
    )

    assert result["status"] == "delivered"
    assert result["event_id"] == "event-1"
    event_insert = query.insert.call_args.args[0]
    assert event_insert["status"] == "triggered"
    assert len(event_insert["evaluation_key"]) == 64
    rule_update = query.update.call_args_list[-1].args[0]
    assert rule_update["last_status"] == "delivered"
    assert rule_update["last_value"] == 120
    assert rule_update["locked_at"] is None


def test_run_claimed_change_alert_records_baseline_without_event(monkeypatch):
    client = MagicMock()
    query = MagicMock()
    client.table.return_value = query
    for method in ("eq", "update"):
        getattr(query, method).return_value = query
    query.execute.return_value = MagicMock(data=[])
    monkeypatch.setattr(
        "app.services.smart_alert_scheduler._evaluate_metric",
        lambda _client, _rule: (
            100.0,
            {"kind": "sum", "field": "Revenue", "label": "Revenue", "value": 100},
            {"row_count": 10, "aggregation_scope": "full_dataset"},
        ),
    )

    result = run_claimed_alert_rule(
        {
            "id": "rule-1",
            "user_id": "user-1",
            "report_id": "report-1",
            "metric_key": "Revenue",
            "operator": "change_gt",
            "threshold": 10,
            "evaluation_interval_minutes": 5,
            "consecutive_failures": 0,
        },
        "worker-1",
        client=client,
    )

    assert result["status"] == "baseline"
    query.insert.assert_not_called()
    update = query.update.call_args.args[0]
    assert update["last_status"] == "baseline"
    assert update["last_value"] == 100
