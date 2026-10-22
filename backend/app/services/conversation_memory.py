"""Dataset key helpers and keyword utilities for chat memory."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_TOKEN_RE = re.compile(r"[\w\u0e00-\u0e7f]+", re.UNICODE)
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "shall", "can", "need", "dare",
        "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by",
        "from", "as", "into", "through", "during", "before", "after", "and",
        "or", "but", "if", "then", "else", "when", "up", "out", "about",
        "what", "which", "who", "whom", "this", "that", "these", "those",
        "am", "it", "its", "my", "your", "his", "her", "our", "their",
        "me", "him", "us", "them", "i", "you", "he", "she", "we", "they",
        "ว่า", "และ", "หรือ", "ใน", "ของ", "ที่", "เป็น", "มี", "ได้", "ไม่",
        "ให้", "กับ", "จาก", "โดย", "นี้", "นั้น", "อะไร", "อย่าง", "แล้ว",
    }
)


def build_dataset_key(
    file_attachment_name: Optional[str],
    connection_id: Optional[str],
    connection_type: Optional[str] = None,
) -> Optional[str]:
    if connection_id:
        return f"conn:{(connection_type or 'unknown').lower()}:{connection_id}"
    if file_attachment_name:
        return f"file:{file_attachment_name}"
    return None


def extract_keywords(text: str, limit: int = 24) -> List[str]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text or "")]
    seen: set[str] = set()
    keywords: List[str] = []
    for token in tokens:
        if len(token) < 2 or token in _STOPWORDS or token in seen:
            continue
        seen.add(token)
        keywords.append(token)
        if len(keywords) >= limit:
            break
    return keywords


def rank_memories(question: str, rows: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    """Score in-memory rows by keyword overlap.

    Designed for lightweight retrieval now; swap scoring for embeddings later
    if memory volume grows beyond keyword overlap quality.
    """
    query_tokens = set(extract_keywords(question, limit=32))
    if not query_tokens:
        return rows[:limit]

    scored: List[tuple[float, Dict[str, Any]]] = []
    for row in rows:
        stored_kw = row.get("keywords") or []
        text = f"{row.get('question', '')} {row.get('insight', '')}"
        candidate_tokens = set(stored_kw) | set(extract_keywords(text, limit=32))
        overlap = len(query_tokens & candidate_tokens)
        if overlap == 0:
            continue
        score = overlap / (len(query_tokens) ** 0.5)
        scored.append((score, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored[:limit]]
