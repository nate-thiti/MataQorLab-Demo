from openai import OpenAI
from typing import Dict
from app.core.config import settings
from app.core.openrouter_routing import openrouter_extra_for_model

client = OpenAI(
    base_url=settings.LLM_BASE_URL,
    api_key=settings.LLM_API_KEY,
)


def _llm_extra_body(model: str) -> dict:
    extra = openrouter_extra_for_model(
        settings.LLM_BASE_URL,
        model,
        (settings.LLM_MODEL_FREE, settings.LLM_MODEL_PREMIUM),
        settings.LLM_PROVIDER_ORDER,
        settings.LLM_PROVIDER_ONLY,
        settings.LLM_PROVIDER_ALLOW_FALLBACKS,
    )
    return extra or {}

def generate_insights(analytics_data: Dict, locale: str = "th") -> str:
    """
    Layer 9: Insight Engine
    ใช้ AI อธิบายผลลัพธ์การวิเคราะห์ข้อมูล
    """
    prompt = f"""
    You are a professional business analyst. Explain the following analytics summary to a business owner.
    
    Data Summary: {analytics_data}
    Language: {locale} (th = Thai, en = English)
    
    Guidelines:
    - Identify the key trend.
    - Highlight the best performing branch/product.
    - Keep it concise and professional.
    - If 'th', use polite business Thai.
    """

    try:
        create_kwargs = {
            "model": settings.LLM_MODEL_FREE,
            "messages": [
                {"role": "system", "content": "You are a helpful business intelligence assistant."},
                {"role": "user", "content": prompt},
            ],
        }
        extra = _llm_extra_body(settings.LLM_MODEL_FREE)
        if extra:
            create_kwargs["extra_body"] = extra
        response = client.chat.completions.create(**create_kwargs)
        return response.choices[0].message.content
    except Exception as e:
        return "Unable to generate insights at this time." if locale == "en" else "ไม่สามารถสร้างบทวิเคราะห์ได้ในขณะนี้"