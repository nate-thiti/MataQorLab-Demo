"""Validate-step readiness gates must stick and clear engine pauses."""
from __future__ import annotations

from app.services.orchestrator.answer_apply import _updates_for_key, parse_simple_answer
from app.services.orchestrator.decision_identity import is_decision_confirmed


def test_approve_option_writes_true_for_business_context():
    updates = _updates_for_key(
        "business_context_reviewed",
        "approve",
        {"id": "approve", "label": "ดำเนินการต่อ"},
    )
    assert updates == {"business_context_reviewed": True}


def test_true_false_options_parse_correctly():
    opts = [
        {"id": "approved", "label": "พร้อมแล้ว", "value": "true"},
        {"id": "modify", "label": "ยังไม่พร้อม", "value": "false"},
    ]
    value, updates = parse_simple_answer(
        "true", decision_key="business_context_reviewed", options=opts
    )
    assert value == "true"
    assert updates == {"business_context_reviewed": True}

    value2, updates2 = parse_simple_answer(
        "false", decision_key="mapping_confirmed", options=opts
    )
    assert value2 == "false"
    assert updates2 == {"mapping_confirmed": False}


def test_false_answer_is_not_treated_as_confirmed():
    session = {
        "id": "s1",
        "source_fingerprint": "fp",
        "column_mapping": {},
        "cleaning_recipe": {"data_contract": {"business_context_reviewed": False}},
        "processing_progress": {
            "confirmed_decisions": {
                "business_context_reviewed": {
                    "value": False,
                    "source": "user_confirmed",
                    "fingerprint": "",
                    "version": 1,
                }
            }
        },
    }
    assert is_decision_confirmed(session, "business_context_reviewed") is False


def test_true_contract_value_is_confirmed():
    session = {
        "id": "s1",
        "source_fingerprint": "fp",
        "column_mapping": {},
        "cleaning_recipe": {"data_contract": {"business_context_reviewed": True}},
        "processing_progress": {},
    }
    assert is_decision_confirmed(session, "business_context_reviewed") is True
