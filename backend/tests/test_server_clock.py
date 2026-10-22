from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.server_clock import (
    build_direct_clock_answer,
    format_clock_prompt_line,
    format_local_answer,
    is_current_datetime_question,
    is_pure_clock_question,
)
from app.services.ai_logic import PromptManager
from app.schemas.chat import Message, ChatRole


def test_detects_thai_and_english_clock_questions():
    assert is_current_datetime_question("ตอนนี้วันที่เท่าไหร่ กี่โมงแล้ว")
    assert is_current_datetime_question("What time is it?")
    assert is_current_datetime_question("What's today's date?")
    assert is_pure_clock_question("ตอนนี้วันที่เท่าไหร่ กี่โมงแล้ว")
    assert is_pure_clock_question("what time is it now")


def test_does_not_treat_analysis_questions_as_pure_clock():
    assert not is_current_datetime_question("สรุปยอดขายวันนี้")
    assert not is_pure_clock_question("วิเคราะห์ยอดขายตอนนี้เทียบเดือนก่อน")
    assert not is_pure_clock_question("What is the current market price?")


def test_fx_rate_today_is_not_pure_clock():
    """Regression: 'วันนี้…เท่าไหร่' must not short-circuit FX to server_clock."""
    q = "ค่าเงิน USD วันนี้อยู่ที่เท่าไหร่"
    assert not is_pure_clock_question(q)
    assert not is_pure_clock_question("USD THB วันนี้เท่าไหร่")
    assert not is_pure_clock_question("อัตราแลก EUR/USD ตอนนี้เท่าไหร่")


def test_direct_clock_answer_uses_bangkok_wall_clock(monkeypatch):
    fixed = datetime(2026, 9, 7, 16, 54, tzinfo=ZoneInfo("Asia/Bangkok"))
    monkeypatch.setattr(
        "app.services.server_clock.server_now",
        lambda **_kwargs: fixed,
    )
    payload = build_direct_clock_answer(locale="th")
    assert "2026" in payload["answer"]
    assert "16:54" in payload["answer"]
    assert payload["tool_execution"]["policy"] == "server_clock"
    assert payload["tool_result"]["engine"] == "server_clock"


def test_prompt_includes_authoritative_server_clock(monkeypatch):
    fixed = datetime(2026, 9, 7, 16, 54, tzinfo=ZoneInfo("Asia/Bangkok"))
    monkeypatch.setattr(
        "app.services.server_clock.server_now",
        lambda **_kwargs: fixed,
    )
    messages = PromptManager.build_messages_for_ai(
        history=[Message(role=ChatRole.USER, content="hello")],
        user_tier="free",
        locale="th",
    )
    system = messages[0]["content"]
    assert "Server wall clock" in system
    assert "2026-09-07" in system
    assert "TIME RULES" in PromptManager.get_system_instruction()


def test_clock_context_injected_for_datetime_questions(monkeypatch):
    fixed = datetime(2026, 9, 7, 16, 54, tzinfo=ZoneInfo("Asia/Bangkok"))
    monkeypatch.setattr(
        "app.services.server_clock.server_now",
        lambda **_kwargs: fixed,
    )
    messages = PromptManager.build_messages_for_ai(
        history=[Message(role=ChatRole.USER, content="ตอนนี้กี่โมง")],
        user_tier="free",
        locale="th",
    )
    user = messages[-1]["content"]
    assert "<server_clock>" in user
    assert "16:54" in user


def test_format_local_answer_english():
    fixed = datetime(2026, 9, 7, 9, 5, tzinfo=ZoneInfo("Asia/Bangkok"))
    text = format_local_answer(fixed, locale="en")
    assert "2026" in text
    assert "09:05" in text
    assert format_clock_prompt_line(fixed).startswith("Server wall clock")


def test_clock_findings_expose_verifier_numbers(monkeypatch):
    from app.services.server_clock import clock_findings, build_server_clock_tool_result

    fixed = datetime(2026, 9, 7, 17, 51, tzinfo=ZoneInfo("Asia/Bangkok"))
    monkeypatch.setattr(
        "app.services.server_clock.server_now",
        lambda **_kwargs: fixed,
    )
    payload = build_server_clock_tool_result(locale="th")
    findings = clock_findings(payload)
    values = {item["value"] for item in findings}
    assert {2026, 9, 7, 17, 51} <= values
