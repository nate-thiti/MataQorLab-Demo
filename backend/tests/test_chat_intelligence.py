import json
from pathlib import Path

import pytest

from app.schemas.chat import ChatRole, Message
from app.services.answer_verifier import verify_answer
from app.services.calculator import calculate_from_question
from app.services.chat_intelligence import (
    build_conversation_memory_summary,
    compact_history,
    infer_user_preferences,
)
from app.services.intent_router import classify_chat_intent
from app.services.chat.llm_client import LlmClient
from app.schemas.chat import ChatRequest, UserTier


def test_intent_router_general_chat():
    decision = classify_chat_intent("ช่วยเขียนอีเมลขอบคุณลูกค้า")
    assert decision.primary == "general_chat"
    assert not decision.needs_web


def test_intent_router_dataset_web_comparison():
    decision = classify_chat_intent(
        "เปรียบเทียบยอดขายกับ industry benchmark ล่าสุด",
        has_dataset=True,
    )
    assert decision.primary == "dataset_web_comparison"
    assert decision.needs_dataset
    assert decision.needs_web
    assert decision.complexity == "high"


def test_intent_router_follow_up():
    decision = classify_chat_intent("แล้วเดือนก่อนล่ะ", history_length=4)
    assert decision.primary == "follow_up"
    assert decision.is_follow_up


def test_safe_calculator():
    result = calculate_from_question("ช่วยคำนวณ (1200 + 300) / 3")
    assert result is not None
    assert result["result"] == 500


def test_safe_calculator_rejects_code():
    assert calculate_from_question("__import__('os').system('id')") is None


def test_safe_calculator_percent_and_average():
    assert calculate_from_question("calculate 15 percent of 800")["result"] == 120
    assert calculate_from_question("ค่าเฉลี่ยของ 10 20 และ 30")["result"] == 20


def test_verifier_marks_grounded_url():
    result = verify_answer(
        "อัตราล่าสุด 35.5 บาท https://example.com/fx",
        web_sources=[
            {
                "title": "FX",
                "url": "https://example.com/fx",
                "snippet": "35.5 THB",
            }
        ],
    )
    assert result["status"] == "grounded"
    assert result["cited_source_count"] == 1


def test_verifier_flags_uncited_external_context():
    result = verify_answer(
        "อัตราล่าสุด 35.5 บาท",
        web_sources=[
            {
                "title": "FX",
                "url": "https://example.com/fx",
                "snippet": "35.5 THB",
            }
        ],
    )
    assert result["status"] == "needs_review"
    assert result["warnings"]


def test_compact_history_keeps_recent_turns():
    history = [
        Message(role=ChatRole.USER, content=f"question {index}")
        for index in range(15)
    ]
    summary, recent = compact_history(history, keep_recent=4)
    assert "question 0" in summary
    assert len(recent) == 4
    assert recent[-1].content == "question 14"


def test_infer_user_preferences():
    preferences = infer_user_preferences("ตอบสั้นๆ เป็น THB")
    assert preferences["language"] == "th"
    assert preferences["answer_style"] == "concise"
    assert preferences["currency"] == "THB"


def test_conversation_memory_summary_never_contains_generated_answer():
    summary = build_conversation_memory_summary("Why did revenue fall?")

    assert "Why did revenue fall?" in summary
    assert summary.startswith("- Focus:")
    assert "\nA:" not in summary


def test_rolling_conversation_memory_accumulates_verified_facts():
    from app.services.chat_intelligence import build_rolling_conversation_memory

    first_summary, first_value = build_rolling_conversation_memory(
        question="Why did revenue fall?",
        conversation_id="c1",
        computed_facts=[{"metric": "net_revenue", "value": 1200, "unit": "THB"}],
    )
    second_summary, second_value = build_rolling_conversation_memory(
        question="Which region dropped most?",
        conversation_id="c1",
        previous_summary=first_summary,
        previous_value=first_value,
        computed_facts=[{"metric": "south_delta", "value": -18, "unit": "%"}],
    )

    assert "Focus: Which region dropped most?" in second_summary
    assert any("net_revenue" in bullet for bullet in second_value["bullets"])
    assert any("south_delta" in bullet for bullet in second_value["bullets"])
    assert len(second_value["decisions"]) >= 2


def test_merge_user_preferences_keeps_prior_fields():
    from app.services.chat_intelligence import merge_user_preferences

    merged = merge_user_preferences(
        {"language": "th", "currency": "THB"},
        {"language": "en", "answer_style": "concise"},
    )
    assert merged["language"] == "en"
    assert merged["currency"] == "THB"
    assert merged["answer_style"] == "concise"


def test_save_user_analysis_preferences_merges_and_clears(monkeypatch):
    from app.services import chat_intelligence

    store = {"value": {"language": "th", "currency": "THB", "answer_style": "detailed"}}

    class FakeTable:
        def __init__(self):
            self.payload = None

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def upsert(self, payload, on_conflict=None):
            self.payload = payload
            store["value"] = payload["value"]
            return self

        def execute(self):
            return type("Resp", (), {"data": [{"summary": "", "value": store["value"], "keywords": []}]})()

    class FakeClient:
        def table(self, _name):
            return FakeTable()

    monkeypatch.setattr(chat_intelligence, "get_supabase_client", FakeClient)
    result = chat_intelligence.save_user_analysis_preferences(
        "user-1",
        {"language": "en", "currency": "AUTO", "answer_style": "concise"},
    )
    assert result["language"] == "en"
    assert result["answer_style"] == "concise"
    assert result["currency"] == ""
    assert "currency" not in store["value"]


def test_prompt_includes_approved_governed_memory_without_raw_rows():
    block = __import__(
        "app.services.ai_logic", fromlist=["PromptManager"]
    ).PromptManager.format_persistent_chat_memory({
        "governed": {"items": [{
            "scope": "workspace",
            "type": "business_definition",
            "title": "Net sales",
            "content": "Gross sales minus approved returns.",
            "confidence": 1,
            "source_hash": "hash-1",
        }]}
    })
    assert "Approved governed context" in block
    assert "Gross sales minus approved returns." in block


def test_verifier_ignores_structural_numbers_but_checks_business_metric():
    result = verify_answer(
        (
            "Revenue is 1,235. Top 10 segments are available. "
            "Here are 2 strategic recommendations using a 95% confidence interval "
            "for the next 3 months."
        ),
        has_dataset_metrics=True,
        structured_findings=[{"metric": "revenue", "value": 1234.567, "unit": "USD"}],
    )

    assert result["status"] == "grounded"
    assert result["dataset_numeric_claim_count"] == 1
    assert len(result["ignored_structural_numeric_claims"]) == 4


def test_verifier_accepts_web_number_when_dataset_is_also_present():
    result = verify_answer(
        "The external rate is 35.5 https://example.com/fx",
        web_sources=[
            {"title": "FX", "url": "https://example.com/fx", "snippet": "Rate 35.5"}
        ],
        has_dataset_metrics=True,
        structured_findings=[{"metric": "revenue", "value": 100, "unit": "USD"}],
    )

    assert result["status"] == "grounded"
    assert result["unmatched_dataset_numeric_claims"] == []


def test_verifier_does_not_require_numeric_evidence_for_general_chat():
    result = verify_answer(
        "ทำตามแผน 3 ขั้นตอน และตั้งงบประมาณตัวอย่างไว้ 100 บาท",
    )

    assert result["status"] == "not_required"
    assert result["evidence_scope_active"] is False
    assert result["unmatched_dataset_numeric_claims"] == []
    assert result["warnings"] == []


def test_model_router_honors_deep_mode_for_paid_tier(monkeypatch):
    from app.services.chat import llm_client as llm_module

    monkeypatch.setattr(llm_module.settings, "LLM_MODEL_REASONING", "reasoning-model")
    monkeypatch.setattr(llm_module.settings, "LLM_MODEL_PREMIUM", "premium-model")
    request = ChatRequest(
        messages=[Message(role=ChatRole.USER, content="วิเคราะห์กลยุทธ์")],
        user_id="user-1",
        tier=UserTier.PRO,
        model_mode="deep",
    )
    model = LlmClient.__new__(LlmClient).resolve_model(
        request,
        intent=classify_chat_intent("วิเคราะห์กลยุทธ์"),
    )
    assert model == "reasoning-model"


def test_model_router_reserves_deep_mode_for_pro(monkeypatch):
    from app.services.chat import llm_client as llm_module

    monkeypatch.setattr(llm_module.settings, "LLM_MODEL_REASONING", "reasoning-model")
    monkeypatch.setattr(llm_module.settings, "LLM_MODEL_PREMIUM", "premium-model")
    request = ChatRequest(
        messages=[Message(role=ChatRole.USER, content="วิเคราะห์กลยุทธ์")],
        user_id="user-1",
        tier=UserTier.PLUS,
        model_mode="deep",
    )
    model = LlmClient.__new__(LlmClient).resolve_model(
        request,
        intent=classify_chat_intent("วิเคราะห์กลยุทธ์"),
    )
    assert model == "premium-model"


def test_model_router_does_not_allow_paid_model_override_on_free_tier(monkeypatch):
    from app.services.chat import llm_client as llm_module

    monkeypatch.setattr(llm_module.settings, "LLM_MODEL_FREE", "free-model")
    monkeypatch.setattr(llm_module.settings, "LLM_MODEL_PREMIUM", "premium-model")
    request = ChatRequest(
        messages=[Message(role=ChatRole.USER, content="hello")],
        user_id="user-1",
        tier=UserTier.FREE,
        model="premium-model",
    )
    model = LlmClient.__new__(LlmClient).resolve_model(request)
    assert model == "free-model"


_REGRESSION_CASES = json.loads(
    (
        Path(__file__).parent
        / "fixtures"
        / "chat_intent_regression.json"
    ).read_text(encoding="utf-8")
)


@pytest.mark.parametrize(
    "case",
    _REGRESSION_CASES,
    ids=[f"intent-{index + 1:02d}" for index in range(len(_REGRESSION_CASES))],
)
def test_chat_intent_regression_corpus(case):
    decision = classify_chat_intent(
        case["question"],
        has_dataset=case.get("has_dataset", False),
        has_connection=case.get("has_connection", False),
        history_length=case.get("history_length", 0),
    )
    assert decision.primary == case["expected"]
