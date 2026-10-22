"""Phase 6 — safe orchestration UI payload."""
from __future__ import annotations

from app.services.orchestrator.decision_models import AskUserDecision, OrchestratorResult, RespondDecision
from app.services.orchestrator.ui_payload import build_orchestration_ui_payload


def test_ui_payload_includes_workflow_tool_result_and_source():
    result = OrchestratorResult(
        decision=RespondDecision(message="ok"),
        assistant_message="ok",
        workflow_plan={
            "session_id": "s1",
            "status": "processing",
            "current_step": "clean",
            "steps": [
                {"step_type": "inspect", "status": "completed", "version": 1},
                {"step_type": "clean", "status": "running", "retryable": False},
            ],
        },
        engine_result={
            "step": "inspect",
            "status": "completed",
            "summary": "scanned",
            "findings": [{"type": "duplicate", "count": 3}],
            "metadata": {"columns": 10, "secret_path": "/tmp/x"},
        },
    )
    payload = build_orchestration_ui_payload(
        result,
        session={
            "id": "s1",
            "status": "processing",
            "source_ref": {"file_name": "sales.xlsx"},
            "scan_result": {"row_count": 100, "column_count": 10},
            "cleaning_recipe": {"data_contract": {"business_context_reviewed": False}},
        },
    )
    assert payload["workflow"]["session_id"] == "s1"
    assert payload["tool_result"]["step_type"] == "inspect"
    assert payload["tool_result"]["findings"][0]["count"] == 3
    assert "secret_path" not in payload["tool_result"]["metadata"]
    assert payload["source"]["name"] == "sales.xlsx"
    assert payload["ready_for_analysis"] is False
    assert payload["assurance"]["data_readiness"] == "pending"
    assert payload["active_decision"] is None


def test_ui_payload_surfaces_session_active_decision():
    result = OrchestratorResult(
        decision=RespondDecision(message="ok"),
        assistant_message="ok",
        workflow_plan={"session_id": "s1", "status": "awaiting_answers", "steps": []},
    )
    payload = build_orchestration_ui_payload(
        result,
        session={
            "id": "s1",
            "status": "awaiting_answers",
            "processing_progress": {
                "active_decision": {
                    "decision_key": "row_grain",
                    "question": "grain?",
                    "options": [{"value": "invoice_line", "label": "Line"}],
                },
            },
        },
    )
    assert payload["active_decision"]["decision_key"] == "row_grain"
    assert payload["awaiting_user"]["decision_key"] == "row_grain"


def test_ui_payload_clears_awaiting_when_no_active_decision():
    result = OrchestratorResult(
        decision=RespondDecision(message="saved"),
        assistant_message="saved",
        awaiting_user={"question": "stale?", "options": []},
        workflow_plan={"session_id": "s1", "status": "processing", "steps": []},
        audit={"actions": [{"decision_type": "collect_input_applied", "decision_key": "row_grain"}]},
    )
    payload = build_orchestration_ui_payload(
        result,
        session={
            "id": "s1",
            "status": "processing",
            "processing_progress": {},
        },
    )
    assert payload["active_decision"] is None
    assert payload["awaiting_user"] is None
    assert payload["resolved_decision_key"] == "row_grain"


def test_ui_payload_keeps_current_ask_answerable_when_session_refresh_lags():
    result = OrchestratorResult(
        decision=AskUserDecision(
            question="ขั้นตอน validate ต้องการอนุมัติหรือไม่?",
            reason="CONFIRMATION_REQUIRED",
            decision_key="confirmation",
            expected_answer_type="option_or_text",
            options=[
                {"id": "approve", "label": "ดำเนินการต่อ"},
                {"id": "reject", "label": "ไม่ดำเนินการ"},
            ],
        ),
        assistant_message="ขั้นตอน validate ต้องการอนุมัติหรือไม่?",
        awaiting_user={
            "decision_key": "confirmation",
            "question": "ขั้นตอน validate ต้องการอนุมัติหรือไม่?",
            "expected_input": "option_or_text",
            "options": [
                {"id": "approve", "label": "ดำเนินการต่อ"},
                {"id": "reject", "label": "ไม่ดำเนินการ"},
            ],
        },
        options=[
            {"id": "approve", "label": "ดำเนินการต่อ"},
            {"id": "reject", "label": "ไม่ดำเนินการ"},
        ],
        workflow_plan={"session_id": "s1", "status": "awaiting_answers", "steps": []},
    )
    payload = build_orchestration_ui_payload(
        result,
        session={"id": "s1", "status": "awaiting_answers", "processing_progress": {}},
    )

    assert payload["active_decision"]["decision_key"] == "confirmation"
    assert payload["active_decision"]["options"][0]["id"] == "approve"
    assert payload["awaiting_user"]["question"].startswith("ขั้นตอน validate")
