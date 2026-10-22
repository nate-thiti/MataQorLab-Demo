from app.core.openrouter_routing import build_openrouter_extra_body, openrouter_extra_for_model


def test_build_openrouter_extra_body_deepinfra():
    extra = build_openrouter_extra_body(
        "https://openrouter.ai/api/v1",
        "deepinfra/bf16",
        "deepinfra/bf16",
        False,
    )
    assert extra == {
        "provider": {
            "order": ["deepinfra/bf16"],
            "only": ["deepinfra/bf16"],
            "allow_fallbacks": False,
        }
    }


def test_build_openrouter_extra_body_skips_non_openrouter():
    assert build_openrouter_extra_body(
        "https://api.groq.com/openai/v1",
        "deepinfra/bf16",
        "",
        False,
    ) is None


def test_openrouter_extra_for_model_skips_fallback():
    assert openrouter_extra_for_model(
        "https://openrouter.ai/api/v1",
        "google/gemma-4-26b-a4b-it:free",
        ("openai/gpt-oss-120b", "google/gemma-4-31b-it"),
        "deepinfra",
        "deepinfra",
        False,
    ) is None


def test_openrouter_extra_for_model_applies_to_primary():
    assert openrouter_extra_for_model(
        "https://openrouter.ai/api/v1",
        "openai/gpt-oss-120b",
        ("openai/gpt-oss-120b", "google/gemma-4-31b-it"),
        "deepinfra",
        "deepinfra",
        False,
    ) == {
        "provider": {
            "order": ["deepinfra"],
            "only": ["deepinfra"],
            "allow_fallbacks": False,
        }
    }


def test_build_openrouter_extra_body_empty_order():
    assert build_openrouter_extra_body(
        "https://openrouter.ai/api/v1",
        "",
        "",
        False,
    ) is None
