import json
from openai import OpenAI
from typing import List, Dict
from app.core.config import settings
from app.core.openrouter_routing import openrouter_extra_for_model

# LLM client (OpenAI-compatible API)
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

CANONICAL_FIELDS = [
    {"field": "date", "description": "Transaction or sales date"},
    {"field": "branch", "description": "Store location, branch name or ID"},
    {"field": "product", "description": "Product name, SKU, or description"},
    {"field": "sales", "description": "Total sales amount, revenue, or price"},
    {"field": "qty", "description": "Quantity sold or stock count"},
    {"field": "category", "description": "Product category or group"}
]

def suggest_schema(columns: List[str], locale: str = "th") -> Dict:
    """
    Layer 3: Schema Detection
    ส่งรายชื่อคอลัมน์ให้ AI ช่วยวิเคราะห์ว่าควร Map เข้ากับ Canonical Field ไหน
    """
    prompt = f"""
    You are a data engineering expert. Map the following user-provided columns to our standard canonical fields.
    
    User Columns: {columns}
    Canonical Fields: {json.dumps(CANONICAL_FIELDS)}
    
    Return ONLY a JSON object where keys are User Columns and values are the matching 'field' name and a confidence score (0-1).
    If no match is found, use null.
    
    Example Output:
    {{
        "ยอดขาย": {{"mapped_to": "sales", "confidence": 0.98}},
        "วันที่": {{"mapped_to": "date", "confidence": 0.95}}
    }}
    """

    try:
        create_kwargs = {
            "model": settings.LLM_MODEL_FREE,
            "messages": [
                {"role": "system", "content": "You are a helpful data analyst that outputs only JSON."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        extra = _llm_extra_body(settings.LLM_MODEL_FREE)
        if extra:
            create_kwargs["extra_body"] = extra
        response = client.chat.completions.create(**create_kwargs)
        
        suggestions = json.loads(response.choices[0].message.content)
        return suggestions
    except Exception as e:
        print(f"AI Schema Detection Error: {e}")
        # Return empty mapping on error
        return {col: {"mapped_to": None, "confidence": 0} for col in columns}