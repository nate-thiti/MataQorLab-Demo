"""Phase 5 — decision parse/validate."""
from __future__ import annotations

import pytest

from app.services.orchestrator.decision_parser import (
    DecisionParseError,
    parse_orchestrator_decision,
)
from app.services.orchestrator.decision_validator import (
    DecisionValidationError,
    validate_decision,
)
from app.services.orchestrator.resolution import parse_user_resolution


def test_parse_valid_ask_user():
    decision = parse_orchestrator_decision(
        '{"type":"ask_user","question":"Approve aggressive clean?","options":[{"id":"approve","label":"Yes"}]}'
    )
    assert decision.type == "ask_user"
    assert "Approve" in decision.question


def test_parse_valid_tool_call():
    decision = parse_orchestrator_decision(
        '{"type":"tool_call","step_type":"clean","reason":"next","proposed_input":{}}'
    )
    assert decision.type == "tool_call"
    assert decision.step_type == "clean"


def test_parse_valid_respond():
    decision = parse_orchestrator_decision('{"type":"respond","message":"hello"}')
    assert decision.type == "respond"


def test_unknown_decision_type_rejected():
    with pytest.raises(DecisionParseError):
        parse_orchestrator_decision('{"type":"run_sql","query":"drop table"}')


def test_malformed_json_rejected():
    with pytest.raises(DecisionParseError):
        parse_orchestrator_decision("not-json")


def test_forbidden_executable_fields_rejected():
    with pytest.raises(DecisionParseError):
        parse_orchestrator_decision(
            '{"type":"tool_call","step_type":"clean","reason":"x","sql":"select 1"}'
        )


def test_unknown_step_rejected_by_validator():
    decision = parse_orchestrator_decision(
        '{"type":"tool_call","step_type":"drop_table","reason":"nope"}'
    )
    with pytest.raises(DecisionValidationError) as exc:
        validate_decision(decision, session={"id": "s1"})
    assert exc.value.code == "UNKNOWN_STEP"


def test_tool_call_requires_session():
    decision = parse_orchestrator_decision(
        '{"type":"tool_call","step_type":"prepare","reason":"go"}'
    )
    with pytest.raises(DecisionValidationError) as exc:
        validate_decision(decision, session=None)
    assert exc.value.code == "SESSION_MISSING"


def test_canonical_step_validated():
    decision = parse_orchestrator_decision(
        '{"type":"tool_call","step_type":"prepare","reason":"go"}'
    )
    out = validate_decision(decision, session={"id": "s1"})
    assert out.step_type == "prepare"


def test_resolution_approve_reject_ambiguous():
    assert parse_user_resolution("ทำเลย").decision == "approved"
    assert parse_user_resolution("ไม่เอา").decision == "rejected"
    assert parse_user_resolution("ก็แล้วแต่").decision == "ambiguous"
    modified = parse_user_resolution("เปลี่ยนเป็น Standard")
    assert modified.decision == "modified"
    assert modified.context_updates["cleaning_profile"] == "standard"
