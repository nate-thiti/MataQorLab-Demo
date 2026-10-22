from app.services.anti_hallucination import (
    build_direct_math_answer,
    definition_askback_message,
    enforce_answer_anti_hallucination,
    is_definition_question,
    is_pure_math_question,
    is_system_status_question,
    needs_live_external_facts,
    refuse_external_facts_message,
    scrub_ungrounded_urls,
)
from app.services.web_search import needs_web_search


def test_live_external_facts_detection():
    assert needs_live_external_facts("USD THB วันนี้เท่าไหร่")
    assert needs_live_external_facts("ราคาทองปัจจุบัน")
    assert needs_live_external_facts("What is the current exchange rate?")
    assert needs_web_search("USD THB วันนี้เท่าไหร่")
    assert not needs_live_external_facts("สรุปยอดขายเดือนนี้")


def test_pure_math_direct_answer():
    assert is_pure_math_question("คำนวณ (1200 + 300) / 3")
    payload = build_direct_math_answer(question="คำนวณ (1200 + 300) / 3", locale="th")
    assert payload is not None
    assert "500" in payload["answer"]
    assert payload["tool_execution"]["policy"] == "safe_calculator"
    assert not is_pure_math_question("คำนวณยอดขายรวมจากไฟล์")


def test_definition_and_status_detectors():
    assert is_definition_question("revenue หมายถึงอะไรในบริษัทเรา")
    assert is_definition_question("What does recognized revenue mean?")
    assert "นิยาม" in definition_askback_message(locale="th")
    assert is_system_status_question("ไฟล์อัปโหลดสำเร็จหรือยัง")
    assert is_system_status_question("Did my ETL schedule finish?")


def test_refuse_external_facts_for_free():
    text = refuse_external_facts_message(locale="th", tier="free")
    assert "Plus" in text or "Pro" in text


def test_scrub_unknown_urls():
    answer = "See https://fake.example/a and https://real.example/b"
    scrubbed, meta = scrub_ungrounded_urls(
        answer,
        [{"url": "https://real.example/b"}],
        thai=False,
    )
    assert meta["applied"] is True
    assert "fake.example" not in scrubbed
    assert "real.example" in scrubbed


def test_enforce_blocks_external_without_sources():
    text, meta = enforce_answer_anti_hallucination(
        "USD/THB is 40.12 today https://made-up.example",
        web_sources=[],
        needs_external=True,
        thai=False,
    )
    assert meta["applied"] is True
    assert "40.12" not in text
    assert "will not invent" in text.lower() or "evidence" in text.lower()


def test_numeric_freeze_for_general_chat():
    text, meta = enforce_answer_anti_hallucination(
        "Revenue grew to 1,250,000 baht this week.",
        web_sources=[],
        needs_external=False,
        thai=False,
        intent_primary="general_chat",
        has_tool_evidence=False,
    )
    assert meta["number_gate"]["applied"] is True
    assert "1,250,000" not in text


def test_follow_up_reattach_detection():
    from app.services.anti_hallucination import follow_up_needs_dataset_reattach

    assert follow_up_needs_dataset_reattach(
        "แล้วเดือนก่อนล่ะ ยอดขายเท่าไหร่",
        has_dataset=False,
        is_follow_up=True,
    )
    assert not follow_up_needs_dataset_reattach(
        "แล้วเดือนก่อนล่ะ",
        has_dataset=True,
        is_follow_up=True,
    )
    # FX / live external must not be blocked by "วันนี้" + follow-up flag.
    assert not follow_up_needs_dataset_reattach(
        "ค่าเงิน USD วันนี้อยู่ที่เท่าไหร่",
        has_dataset=False,
        is_follow_up=True,
    )
    assert not follow_up_needs_dataset_reattach(
        "USD THB วันนี้เท่าไหร่",
        has_dataset=False,
        is_follow_up=True,
    )


def test_short_fx_question_is_not_follow_up():
    from app.services.intent_router import classify_chat_intent

    decision = classify_chat_intent(
        "ค่าเงิน USD วันนี้อยู่ที่เท่าไหร่",
        history_length=6,
    )
    assert decision.primary == "web_research"
    assert decision.needs_web is True
    assert decision.is_follow_up is False
    assert decision.needs_calculator is False


def test_weather_forecast_is_not_calculator_intent():
    from app.services.intent_router import classify_chat_intent

    decision = classify_chat_intent(
        "พยากรณ์อากาศวันนี้ล่ะ ฉะเชิงเทรา",
        history_length=2,
    )
    assert decision.needs_calculator is False
    assert decision.needs_web is True



def test_chart_validation_without_findings():
    from app.services.anti_hallucination import validate_chart_actions

    answer = """Here is a chart.

```json
{"action":"render_chart","chart_type":"bar","data":[{"name":"A","value":999}]}
```
"""
    scrubbed, meta = validate_chart_actions(answer, structured_findings=[], thai=False)
    assert meta["applied"] is True
    assert "render_chart" not in scrubbed
