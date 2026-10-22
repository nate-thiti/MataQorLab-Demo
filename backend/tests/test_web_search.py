from unittest.mock import MagicMock, patch

from app.services.question_analytics import merge_into_analytics
from app.services.web_search import (
    build_web_search_step,
    dedupe_web_sources,
    inject_web_search_steps,
    is_web_search_step,
    merge_web_search_with_result,
    needs_web_search,
    normalize_web_search_query,
    run_web_search,
    run_multi_web_search,
    generate_web_search_queries,
    web_search_enabled,
)
from app.services.ai_logic import PromptManager
from app.schemas.chat import Message, ChatRole


def test_web_search_enabled_tiers():
    assert web_search_enabled("plus")
    assert web_search_enabled("pro")
    assert not web_search_enabled("free")


def test_needs_web_search_detects_external_intent():
    assert needs_web_search("Compare our growth with industry benchmark")
    assert needs_web_search("อัตราแลก USD THB ล่าสุดเทียบกับยอดขาย")
    assert not needs_web_search("ยอดขายตามภาค")
    assert not needs_web_search("short")


def test_needs_web_search_detects_currency_pairs_and_current_dates():
    assert needs_web_search("JPY เป็น THB เท่าไหร่")
    assert needs_web_search("EUR/USD")
    assert needs_web_search("ราคาทองปัจจุบันเทียบกับตลาด")
    assert needs_web_search("What is the current market price?")
    assert not needs_web_search("สรุปยอดขายวันที่ 2026-07-01")


def test_generate_queries_expands_single_usd_fx_ask():
    queries = generate_web_search_queries("ค่าเงิน 1 USD วันนี้อยู่ที่เท่าไหร่")
    assert any("USD THB" in q.upper() for q in queries)
    assert any("exchange rate" in q.lower() for q in queries)
    assert queries[0].upper().startswith("USD")


def test_generate_queries_focuses_fx_in_combined_clock_ask():
    queries = generate_web_search_queries(
        "ค่าเงิน 1 USD วันนี้อยู่ที่เท่าไหร่ และ วันนี้วันที่เท่าไหร่"
    )
    assert queries
    assert "USD THB" in queries[0].upper()
    assert "whatsapp" not in " ".join(queries).lower()


def test_filter_web_sources_drops_whatsapp_for_fx():
    from app.services.web_search import filter_web_sources_for_question

    sources = [
        {
            "title": "Download WhatsApp",
            "url": "https://www.whatsapp.com/download",
            "snippet": "Message privately",
        },
        {
            "title": "USD THB exchange rate",
            "url": "https://www.bot.or.th/fx",
            "snippet": "USD/THB spot rate today",
        },
    ]
    cleaned = filter_web_sources_for_question(
        sources,
        "ค่าเงิน 1 USD วันนี้อยู่ที่เท่าไหร่",
    )
    assert len(cleaned) == 1
    assert "bot.or.th" in cleaned[0]["url"]


def test_generate_web_search_queries_for_currency():
    queries = generate_web_search_queries("USD/THB วันนี้")
    assert len(queries) == 3
    assert any("official" in query for query in queries)


def test_inject_web_search_steps_no_longer_keyword_forces():
    steps = inject_web_search_steps(["Analyze revenue"], "Compare with market benchmark", "plus")
    assert steps == ["Analyze revenue"]
    steps_again = inject_web_search_steps(steps, "Compare with market benchmark", "plus")
    assert steps_again == ["Analyze revenue"]


def test_inject_web_search_skips_free_tier():
    steps = inject_web_search_steps(["Analyze revenue"], "Compare with market benchmark", "free")
    assert steps == ["Analyze revenue"]


def test_merge_web_search_with_result():
    merged = merge_web_search_with_result(
        {"formatted": "dataset stats", "success": True},
        {
            "formatted": "Web Search Results for 'GDP'",
            "web_sources": [{"title": "GDP", "url": "https://example.com", "snippet": "x"}],
        },
    )
    assert "External Web Context" in merged["formatted"]
    assert "dataset stats" in merged["formatted"]
    assert len(merged["web_sources"]) == 1


def test_prompt_includes_web_search_for_plus():
    prompt = PromptManager.get_system_instruction(user_tier="plus")
    assert "WEB SEARCH" in prompt
    assert "DuckDuckGo" in prompt


def test_prompt_omits_web_search_for_free():
    prompt = PromptManager.get_system_instruction(user_tier="free")
    assert "WEB SEARCH" not in prompt


def test_prompt_attaches_web_context_without_dataset():
    messages = PromptManager.build_messages_for_ai(
        history=[
            Message(role=ChatRole.USER, content="USD THB วันนี้"),
        ],
        user_tier="plus",
        external_web_result={
            "formatted": "Web Search Results for 'USD THB'",
            "web_sources": [
                {
                    "title": "FX source",
                    "url": "https://example.com/fx",
                    "snippet": "Current rate",
                }
            ],
        },
    )
    assert "<external_web_context>" in messages[-1]["content"]
    assert "https://example.com/fx" in messages[-1]["content"]


def test_is_web_search_step():
    assert is_web_search_step("web_search: Thailand GDP 2025")
    assert not is_web_search_step("Calculate revenue by region")


def test_normalize_web_search_query_strips_user_context():
    step = "web_search: USD THB rate (User context: compare to last month)"
    assert normalize_web_search_query(step) == "USD THB rate"


def test_dedupe_web_sources_by_url():
    sources = dedupe_web_sources(
        [
            {"title": "A", "url": "https://example.com/a", "snippet": "one"},
            {"title": "A duplicate", "url": "https://example.com/a", "snippet": "two"},
            {"title": "B", "url": "https://example.com/b", "snippet": "three"},
        ]
    )
    assert len(sources) == 2
    assert sources[0]["url"] == "https://example.com/a"
    assert sources[1]["url"] == "https://example.com/b"


@patch("app.services.web_search.DDGS")
def test_run_web_search_success(mock_ddgs_cls):
    mock_ddgs = MagicMock()
    mock_ddgs.__enter__.return_value = mock_ddgs
    mock_ddgs.text.return_value = [
        {
            "title": "Thailand GDP",
            "href": "https://example.com/gdp",
            "body": "Latest GDP figures",
        }
    ]
    mock_ddgs_cls.return_value = mock_ddgs

    result = run_web_search("Thailand GDP")

    assert result["success"] is True
    assert result["engine"] == "web_search"
    assert len(result["web_sources"]) == 1
    assert result["web_sources"][0]["url"] == "https://example.com/gdp"
    assert "Thailand GDP" in result["formatted"]


@patch("app.services.web_search.DDGS")
def test_run_web_search_no_results(mock_ddgs_cls):
    mock_ddgs = MagicMock()
    mock_ddgs.__enter__.return_value = mock_ddgs
    mock_ddgs.text.return_value = []
    mock_ddgs_cls.return_value = mock_ddgs

    result = run_web_search("unknown query xyz")

    assert result["success"] is True
    assert result["web_sources"] == []
    assert "No web search results found" in result["formatted"]


@patch("app.services.web_search.DDGS")
def test_run_web_search_failure(mock_ddgs_cls):
    mock_ddgs_cls.side_effect = RuntimeError("network down")

    result = run_web_search("Thailand GDP")

    assert result["success"] is False
    assert "Web search failed" in result["formatted"]


@patch("app.services.web_search.run_web_search")
def test_run_multi_web_search_dedupes_and_ranks(mock_run):
    mock_run.side_effect = lambda query, max_results: {
        "success": True,
        "web_sources": [
            {
                "title": "Bank of Thailand FX",
                "url": "https://www.bot.or.th/fx",
                "snippet": "USD THB exchange rate today",
                "query": query,
            },
            {
                "title": "Duplicate",
                "url": "https://www.bot.or.th/fx",
                "snippet": "duplicate",
                "query": query,
            },
        ],
    }
    result = run_multi_web_search("USD THB today")
    assert len(result["queries"]) == 3
    assert len(result["web_sources"]) == 1
    assert result["web_sources"][0]["score"] > 0.5


def test_merge_into_analytics_collects_web_sources():
    merged = merge_into_analytics(
        {},
        {
            "formatted": "combined",
            "steps": [
                {"web_sources": [{"title": "A", "url": "https://a.test", "snippet": "a"}]},
                {"web_sources": [{"title": "A2", "url": "https://a.test", "snippet": "dup"}]},
            ],
        },
    )

    assert len(merged["web_sources"]) == 1
    assert merged["web_sources"][0]["url"] == "https://a.test"
