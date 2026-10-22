"""Tests for lightweight conversation / dataset insight memory."""
from app.services.conversation_memory import (
    build_dataset_key,
    extract_keywords,
    rank_memories,
)


def test_build_dataset_key_file():
    assert build_dataset_key("sales.csv", None) == "file:sales.csv"


def test_build_dataset_key_connection():
    assert build_dataset_key(None, "conn-1", "sql") == "conn:sql:conn-1"


def test_build_dataset_key_empty():
    assert build_dataset_key(None, None) is None


def test_extract_keywords_filters_stopwords():
    keywords = extract_keywords("สรุปยอดขายรายเดือน monthly sales report")
    assert "sales" in keywords
    assert "the" not in keywords


def test_rank_memories_prefers_overlap():
    rows = [
        {
            "question": "inventory turnover by branch",
            "insight": "Branch A has highest turnover",
            "keywords": ["inventory", "turnover", "branch"],
        },
        {
            "question": "marketing ROAS by channel",
            "insight": "Facebook leads on ROAS",
            "keywords": ["marketing", "roas", "channel"],
        },
    ]
    ranked = rank_memories("inventory turnover branch A", rows, limit=1)
    assert len(ranked) == 1
    assert "inventory" in ranked[0]["question"]
