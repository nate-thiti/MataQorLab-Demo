from app.schemas.chat import sanitize_message_content


def test_sanitize_message_content_hides_internal_context_markup():
    content = (
        "<calculated_metrics> External Web Context (pre-fetched by platform):\n"
        "- Latest weather evidence\n"
        "</calculated_metrics>\n"
        "<web_sources>https://example.com/weather</web_sources>"
    )

    cleaned = sanitize_message_content(content)

    assert "<calculated_metrics>" not in cleaned
    assert "<web_sources>" not in cleaned
    assert "pre-fetched by platform" not in cleaned
    assert "Latest weather evidence" in cleaned
    assert "https://example.com/weather" in cleaned


def test_sanitize_message_content_keeps_internal_tag_examples_in_code_fences():
    content = "```xml\n<calculated_metrics>example</calculated_metrics>\n```"

    assert sanitize_message_content(content) == content
