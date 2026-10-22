from datetime import datetime, timedelta, timezone

from app.services.automation_guardrails import (
    evaluate_delivery_candidate,
    normalize_automation_config,
)


def _ready_config():
    return {
        "delivery_enabled": True,
        "recipient_opt_in": True,
        "recipient": "manager@example.com",
        "preview_acknowledged": True,
        "require_complete_period": True,
        "cooldown_minutes": 60,
        "max_source_age_hours": 48,
    }


def test_candidate_is_eligible_only_when_all_gates_pass():
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    decision = evaluate_delivery_candidate(
        config=_ready_config(),
        data_contract={"period_status": "complete"},
        fingerprint="new",
        previous_fingerprint="old",
        current_rows=110,
        previous_rows=100,
        source_updated_at=(now - timedelta(hours=2)).isoformat(),
        now=now,
    )
    assert decision["decision"] == "eligible"
    assert decision["delivery_sent"] is False


def test_duplicate_incomplete_stale_and_cooldown_are_suppressed():
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    decision = evaluate_delivery_candidate(
        config=_ready_config(),
        data_contract={"period_status": "in_progress"},
        fingerprint="same",
        previous_fingerprint="same",
        current_rows=100,
        previous_rows=100,
        source_updated_at=(now - timedelta(hours=72)).isoformat(),
        last_eligible_at=(now - timedelta(minutes=10)).isoformat(),
        now=now,
    )
    assert decision["decision"] == "suppressed"
    assert {
        "incomplete_period",
        "stale_source",
        "duplicate_fingerprint",
        "cooldown_active",
    }.issubset(decision["reason_codes"])


def test_config_is_bounded_and_delivery_defaults_off():
    config = normalize_automation_config({
        "cooldown_minutes": 999999,
        "max_source_age_hours": 0,
        "significant_change_percent": 1000,
    })
    assert config["delivery_enabled"] is False
    assert config["cooldown_minutes"] == 43200
    assert config["max_source_age_hours"] == 48
    assert config["significant_change_percent"] == 100


def test_semantic_kpi_change_gate_uses_verified_aggregates():
    config = {
        **_ready_config(),
        "significant_kpi_change_percent": 5,
    }
    decision = evaluate_delivery_candidate(
        config=config,
        data_contract={"period_status": "complete"},
        fingerprint="new",
        previous_fingerprint="old",
        current_rows=101,
        previous_rows=100,
        current_kpis={"revenue": 1020.0, "orders": 100.0},
        previous_kpis={"revenue": 1000.0, "orders": 100.0},
        source_updated_at=datetime.now(timezone.utc).isoformat(),
    )
    assert decision["decision"] == "suppressed"
    assert "kpi_change_below_threshold" in decision["reason_codes"]
    assert decision["kpi_changes"]["revenue"] == 2.0


def test_chat_only_delivery_does_not_require_an_email_recipient():
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    config = {
        **_ready_config(),
        "delivery_enabled": False,
        "recipient_opt_in": False,
        "recipient": "",
    }
    decision = evaluate_delivery_candidate(
        config=config,
        data_contract={"period_status": "complete"},
        fingerprint="new",
        previous_fingerprint="old",
        current_rows=100,
        previous_rows=None,
        source_updated_at=now.isoformat(),
        now=now,
        delivery_channels=["chat"],
        chat_target_valid=True,
    )
    assert decision["decision"] == "eligible"
    assert decision["delivery_channels"] == ["chat"]
    assert "recipient_not_opted_in" not in decision["reason_codes"]


def test_chat_delivery_requires_a_valid_owned_target():
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    decision = evaluate_delivery_candidate(
        config={**_ready_config(), "delivery_enabled": False},
        data_contract={"period_status": "complete"},
        fingerprint="new",
        previous_fingerprint=None,
        current_rows=100,
        previous_rows=None,
        source_updated_at=now.isoformat(),
        now=now,
        delivery_channels=["chat"],
        chat_target_valid=False,
    )
    assert decision["decision"] == "suppressed"
    assert "chat_target_invalid" in decision["reason_codes"]
