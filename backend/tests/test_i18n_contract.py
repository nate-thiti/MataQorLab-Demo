from pydantic import ValidationError

from app.schemas.chat import ChatRequest, Message
from app.services.chat.context_builder import _add_locale_instruction


def _request(**updates):
    payload = {
        "messages": [Message(role="user", content="")],
        "user_id": "00000000-0000-4000-8000-000000000001",
        **updates,
    }
    return ChatRequest(**payload)


def test_chat_request_carries_a_supported_ui_locale():
    assert _request(locale="en").locale == "en"
    assert _request().locale == "th"

    try:
        _request(locale="fr")
    except ValidationError:
        pass
    else:
        raise AssertionError("unsupported chat locale must be rejected")


def test_chat_prompt_gets_an_explicit_locale_instruction():
    messages = [{"role": "system", "content": "base"}]
    _add_locale_instruction(messages, "en")

    assert messages[1]["role"] == "system"
    assert "selected UI language is English" in messages[1]["content"]
