from app.services.intent_router import classify_chat_intent
from app.services.response_mode import resolve_response_mode


def _intent(question: str, *, has_dataset: bool = False):
    return classify_chat_intent(
        question,
        has_dataset=has_dataset,
        history_length=0,
    )


def test_fast_has_small_but_verified_execution_budget():
    policy = resolve_response_mode("fast", _intent("Summarize this", has_dataset=True))

    assert policy.effective == "fast"
    assert policy.max_agent_steps == 2
    assert policy.max_search_queries == 1
    assert policy.max_search_sources == 4
    assert policy.max_output_tokens == 900


def test_deep_uses_full_execution_budget_and_respects_server_cap():
    policy = resolve_response_mode(
        "deep",
        _intent("Analyze root cause and trade-offs", has_dataset=True),
        agent_step_cap=4,
    )

    assert policy.effective == "deep"
    assert policy.max_agent_steps == 4
    assert policy.max_search_queries == 3
    assert policy.max_search_sources == 8
    assert policy.max_output_tokens == 4096


def test_auto_uses_fast_for_simple_chat_and_deep_for_external_or_dataset_work():
    simple = resolve_response_mode("auto", _intent("สวัสดี"))
    external = resolve_response_mode("auto", _intent("อัตราแลก USD/THB วันนี้"))
    dataset = resolve_response_mode(
        "auto",
        _intent("สรุปข้อมูลนี้", has_dataset=True),
    )

    assert simple.effective == "fast"
    assert external.effective == "deep"
    assert dataset.effective == "deep"


def test_output_token_request_can_only_reduce_server_budget():
    fast = resolve_response_mode("fast", _intent("hello"))

    assert fast.output_tokens(None) == 900
    assert fast.output_tokens(400) == 400
    assert fast.output_tokens(9999) == 900
