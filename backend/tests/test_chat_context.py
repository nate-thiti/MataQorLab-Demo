"""Tests for chat context assembly (connection mentions, LLM payload)."""
from app.services.ai_logic import PromptManager
from app.services.chat.context_builder import (
    _visualization_context_matches_explicit_source,
)
from app.services.chat.pipeline import strip_connection_mention
from app.schemas.chat import ChatRequest, Message, ChatRole


def test_strip_connection_mention():
    assert strip_connection_mention("@SalesDB-orders total revenue") == "total revenue"
    assert strip_connection_mention("@MyAPI compare Q1 vs Q2") == "compare Q1 vs Q2"
    assert strip_connection_mention("plain question") == "plain question"


def test_visualization_context_explicit_source_precedence():
    base = {
        "messages": [{"role": "user", "content": "compare this"}],
        "user_id": "user-1",
    }
    report_file = {"type": "file", "file_name": "report.csv", "connection_id": None}

    assert _visualization_context_matches_explicit_source(
        report_file,
        ChatRequest(**base, file_attachment_name="report.csv"),
    )
    assert not _visualization_context_matches_explicit_source(
        report_file,
        ChatRequest(**base, file_attachment_name="replacement.csv"),
    )
    assert not _visualization_context_matches_explicit_source(
        report_file,
        ChatRequest(**base, connection_id="connection-2", connection_type="sql"),
    )


def test_build_messages_includes_analytics_without_file_content():
    analytics = {
        "formatted_notes": "=== Dataset Overview (100 rows) ===\n- sales sum=1000",
        "column_profile": "- sales (DOUBLE): null 0%",
    }
    messages = PromptManager.build_messages_for_ai(
        history=[Message(role=ChatRole.USER, content="What is total sales?")],
        file_name="api_response.json",
        file_content=None,
        analytics_results=analytics,
        user_tier="plus",
    )
    user_msg = messages[-1]["content"]
    assert "<calculated_metrics>" in user_msg
    assert "1000" in user_msg
    assert "WEB SEARCH" in messages[0]["content"]


def test_prompt_has_conditional_outline_contract_without_duplicate_table_instruction():
    prompt = PromptManager.get_system_instruction()

    assert "When `<server_response_outline>` exists" in prompt
    assert "continue directly with interpretation" in prompt
    assert "The server executes selected tools." in prompt
    assert "Never simulate a tool result" in prompt
    assert "Structure: key findings → table if helpful" not in prompt


def test_structured_findings_prompt_is_compact():
    context = PromptManager.format_file_context(
        "sales.csv",
        "10 rows",
        analytics_results={
            "structured_findings": [
                {
                    "id": "f_1",
                    "metric": "revenue",
                    "value": 100,
                    "unit": "USD",
                    "evidence": "Computed on all rows.",
                    "interpretation": "must not be sent",
                    "suggested_action": "must not be sent",
                    "provenance": {"query_hash": "large"},
                    "audit": {"sql": "SELECT secret"},
                }
            ]
        },
    )

    findings_block = context.split("<structured_findings>", 1)[1].split(
        "</structured_findings>", 1
    )[0]
    assert '"id": "f_1"' in findings_block
    assert '"evidence": "Computed on all rows."' in findings_block
    assert "interpretation" not in findings_block
    assert "provenance" not in findings_block
    assert "SELECT secret" not in findings_block
