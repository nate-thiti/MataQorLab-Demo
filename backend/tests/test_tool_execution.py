from app.services.answer_verifier import verify_answer
from app.services.tool_execution import (
    build_tool_execution,
    calculator_findings,
    enforce_tool_grounding,
    tool_gate_message,
)


def test_calculator_becomes_server_owned_numeric_evidence():
    result = {
        "engine": "safe_calculator",
        "expression": "20% of 50",
        "result": 10,
        "formatted": "Verified calculator result: 20% of 50 = 10",
    }

    findings = calculator_findings(result)
    verification = verify_answer(
        "20% of 50 equals 10.",
        has_dataset_metrics=True,
        structured_findings=findings,
    )

    assert {item["value"] for item in findings} == {10, 20, 50}
    assert all(item["provenance"]["engine"] == "safe_calculator" for item in findings)
    assert verification["status"] == "grounded"
    assert verification["unmatched_dataset_numeric_claims"] == []


def test_required_calculator_failure_blocks_model_fallback():
    execution = build_tool_execution(
        {
            "needs_dataset": False,
            "needs_calculator": True,
            "needs_web": False,
        },
        calculator_result=None,
    )

    assert execution["policy"] == "tool_first_compute_only"
    assert execution["satisfied"] is False
    assert execution["missing"] == ["safe_calculator"]
    assert "จะไม่ให้ AI คำนวณ" in tool_gate_message(execution, thai=True)


def test_model_selected_web_ignores_keyword_calculator_requirement():
    """Weather/FX must not pull safe_calculator just because intent keywords fired."""
    execution = build_tool_execution(
        {
            "needs_dataset": False,
            "needs_calculator": True,
            "needs_web": True,
        },
        selected_tools=["web_search"],
        calculator_result=None,
        web_result={
            "queries": ["weather Chachoengsao"],
            "web_sources": [{"url": "https://example.com/weather", "snippet": "32C"}],
        },
    )
    assert execution["policy"] == "model_selected_tools"
    assert execution["required"] == ["web_search"]
    assert execution["satisfied"] is True
    assert execution["missing"] == []


def test_server_clock_counts_as_tool_evidence():
    execution = build_tool_execution(
        {"needs_dataset": False, "needs_calculator": False, "needs_web": False},
        selected_tools=["server_clock"],
        clock_result={
            "success": True,
            "iso": "2026-09-07T17:51:00+07:00",
            "answer": "ขณะนี้วันที่ 7 กันยายน 2026 เวลา 17:51 น. (+07)",
        },
    )
    assert execution["satisfied"] is True
    assert execution["numeric_evidence_available"] is True
    assert execution["tool_evidence_available"] is True
    assert tool_gate_message(execution, thai=True) is None


def test_web_only_failure_message_is_explicit():
    execution = build_tool_execution(
        {"needs_dataset": False, "needs_calculator": False, "needs_web": True},
        selected_tools=["web_search"],
        web_result={"queries": ["USD"], "web_sources": []},
    )
    assert execution["satisfied"] is False
    msg = tool_gate_message(execution, thai=True)
    assert msg is not None
    assert "แหล่ง" in msg
    assert "safe_calculator" not in msg


def test_dataset_and_web_calls_are_visible_in_execution_ledger():
    execution = build_tool_execution(
        {
            "needs_dataset": True,
            "needs_calculator": True,
            "needs_web": True,
        },
        analytics_results={
            "question_aware": {"success": True, "engine": "duckdb"},
            "structured_findings": [{"id": "f_1", "value": 100}],
        },
        web_result={
            "queries": ["benchmark"],
            "web_sources": [{"url": "https://example.com", "snippet": "100"}],
        },
    )

    assert execution["satisfied"] is True
    assert [call["tool"] for call in execution["calls"]] == [
        "dataset_query",
        "web_search",
    ]
    assert all(call["server_executed"] is True for call in execution["calls"])


def test_typed_agent_calls_and_evidence_are_visible_in_execution_ledger():
    execution = build_tool_execution(
        {"needs_dataset": True, "needs_calculator": False, "needs_web": False},
        analytics_results={
            "question_aware": {"success": True, "engine": "duckdb"},
            "structured_findings": [
                {"id": "f_metric", "type": "agent_compute_metrics", "value": 125},
            ],
            "agent_tool_calls": [{
                "call_id": "call_metric",
                "tool_id": "compute_metrics",
                "status": "completed",
                "attempts": 1,
                "duration_ms": 4,
                "output_summary": {"engine": "duckdb"},
            }],
        },
    )

    typed = next(call for call in execution["calls"] if call["tool"] == "compute_metrics")
    assert typed["status"] == "completed"
    assert typed["numeric_evidence"] is True
    assert typed["evidence_ids"] == ["f_metric"]


def test_completed_but_ineligible_tool_is_semantically_failed_in_ledger():
    execution = build_tool_execution(
        {"needs_dataset": True, "needs_calculator": False, "needs_web": False},
        analytics_results={
            "question_aware": {"success": True, "engine": "duckdb"},
            "structured_findings": [{"id": "f_base", "type": "dataset_size", "value": 2}],
            "agent_tool_calls": [{
                "call_id": "call_forecast",
                "tool_id": "forecast_series",
                "status": "completed",
                "output_summary": {
                    "success": False,
                    "eligible": False,
                    "reason": "Forecast requires at least 6 monthly periods.",
                },
            }],
        },
    )

    forecast = next(call for call in execution["calls"] if call["tool"] == "forecast_series")
    assert forecast["status"] == "failed"
    assert forecast["numeric_evidence"] is False
    assert "6 monthly periods" in forecast["error"]


def test_fail_closed_gate_removes_unsupported_numeric_line():
    draft = "ยอดขายลดลง 99%\nควรตรวจสอบสาเหตุเชิงธุรกิจเพิ่มเติม"
    verification = verify_answer(
        draft,
        has_dataset_metrics=True,
        structured_findings=[{"metric": "growth", "value": 12, "unit": "%"}],
    )

    safe, gate = enforce_tool_grounding(draft, verification, thai=True)

    assert gate["applied"] is True
    assert "99%" not in safe
    assert "ควรตรวจสอบ" in safe
    assert "หลักฐานจากเครื่องมือ" in safe


def test_fail_closed_gate_withholds_answer_when_verifier_is_unavailable():
    safe, gate = enforce_tool_grounding(
        "Revenue is 999.",
        {
            "status": "needs_review",
            "evidence_count": 1,
            "warnings": ["Answer verification was unavailable for this response."],
        },
        thai=False,
    )

    assert gate["reason"] == "verifier_unavailable"
    assert "999" not in safe
    assert "withheld" in safe


def test_grounding_gate_preserves_numbers_when_chat_has_no_tool_evidence():
    draft = "แนะนำ 3 ขั้นตอน และใช้งบประมาณตัวอย่าง 100 บาท"
    verification = verify_answer(draft)

    safe, gate = enforce_tool_grounding(draft, verification, thai=True)

    assert safe == draft
    assert gate["applied"] is False
    assert gate["reason"] == "no_tool_evidence"


def test_fail_closed_gate_removes_whole_unsupported_chart_command():
    draft = (
        "Chart draft\n"
        "```json\n"
        '{"action":"render_chart","data":[{"name":"A","value":999}]}\n'
        "```"
    )
    verification = verify_answer(
        draft,
        has_dataset_metrics=True,
        structured_findings=[{"metric": "value", "value": 10, "unit": ""}],
    )

    safe, gate = enforce_tool_grounding(draft, verification, thai=False)

    assert gate["applied"] is True
    assert "render_chart" not in safe
    assert "999" not in safe
