"""Persistent chat memory and quality telemetry (best effort, never blocks chat)."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.supabase import get_supabase_client
from app.services.conversation_memory import extract_keywords, rank_memories


MAX_WORKING_BULLETS = 8
MAX_DECISIONS = 6
MAX_SUMMARY_CHARS = 1800


def compact_history(
    history: List[Any],
    *,
    keep_recent: int = 12,
    summary_chars: int = 2400,
) -> tuple[str, List[Any]]:
    """Keep recent turns verbatim and compact older turns into a bounded summary."""
    if len(history) <= keep_recent:
        return "", list(history)
    older = history[:-keep_recent]
    recent = history[-keep_recent:]
    lines: List[str] = []
    for message in older:
        role = getattr(getattr(message, "role", None), "value", None) or getattr(
            message, "role", "unknown"
        )
        content = " ".join((getattr(message, "content", "") or "").split())
        if content:
            lines.append(f"{role}: {content[:360]}")
    summary = "\n".join(lines)
    if len(summary) > summary_chars:
        summary = summary[-summary_chars:]
    return summary, list(recent)


def infer_user_preferences(question: str) -> Dict[str, Any]:
    text = (question or "").strip()
    lower = text.lower()
    prefs: Dict[str, Any] = {
        "language": "th" if any("\u0e00" <= char <= "\u0e7f" for char in text) else "en"
    }
    if any(term in lower for term in ("สั้นๆ", "สั้น ๆ", "กระชับ", "concise", "brief")):
        prefs["answer_style"] = "concise"
    elif any(term in lower for term in ("ละเอียด", "เจาะลึก", "detailed", "deep dive")):
        prefs["answer_style"] = "detailed"
    for currency in ("THB", "USD", "EUR", "GBP", "JPY", "CNY", "SGD"):
        if currency.lower() in lower:
            prefs["currency"] = currency
            break
    return prefs


def merge_user_preferences(
    existing: Optional[Dict[str, Any]],
    inferred: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Deep-merge preference fields; never wipe earlier confirmed prefs."""
    merged: Dict[str, Any] = {}
    if isinstance(existing, dict):
        merged.update(existing)
    for key, value in (inferred or {}).items():
        if value is None or value == "":
            continue
        merged[key] = value
    return merged


def _fact_bullet(item: Dict[str, Any]) -> Optional[str]:
    metric = str(item.get("metric") or item.get("type") or "").strip()
    value = item.get("value")
    unit = str(item.get("unit") or "").strip()
    if metric and value is not None:
        label = f"{metric} = {value}"
        if unit:
            label = f"{label} {unit}"
        return label.strip()[:220]
    evidence = item.get("evidence")
    if isinstance(evidence, str) and evidence.strip():
        return evidence.strip()[:220]
    return None


def build_conversation_memory_summary(
    question: str,
    *,
    previous_summary: str = "",
    previous_value: Optional[Dict[str, Any]] = None,
    computed_facts: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build a bounded rolling working-notes summary (never stores answer prose)."""
    _summary, value = build_rolling_conversation_memory(
        question=question,
        previous_summary=previous_summary,
        previous_value=previous_value,
        computed_facts=computed_facts,
    )
    return value.get("summary_text") or _summary


def build_rolling_conversation_memory(
    *,
    question: str,
    conversation_id: Optional[str] = None,
    previous_summary: str = "",
    previous_value: Optional[Dict[str, Any]] = None,
    computed_facts: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Accumulate working notes + verified decisions without storing generated answers."""
    previous_value = previous_value if isinstance(previous_value, dict) else {}
    prior_bullets = [
        str(item).strip()
        for item in list(previous_value.get("bullets") or [])
        if str(item).strip()
    ]
    if not prior_bullets and previous_summary:
        for line in previous_summary.splitlines():
            cleaned = line.strip().lstrip("-• ").strip()
            if cleaned.lower().startswith("user question:"):
                cleaned = cleaned.split(":", 1)[-1].strip()
                if cleaned:
                    prior_bullets.append(f"Focus: {cleaned[:200]}")
            elif cleaned:
                prior_bullets.append(cleaned[:220])

    focus = " ".join((question or "").split()).strip()[:220]
    bullets: List[str] = []
    if focus:
        bullets.append(f"Focus: {focus}")

    decisions: List[Dict[str, Any]] = []
    for item in list(previous_value.get("decisions") or [])[:MAX_DECISIONS]:
        if isinstance(item, dict) and item.get("statement"):
            decisions.append(item)

    facts = list(computed_facts or [])[:24]
    for item in facts:
        if not isinstance(item, dict):
            continue
        statement = _fact_bullet(item)
        if not statement:
            continue
        bullets.append(f"Verified: {statement}")
        decisions.append(
            {
                "statement": statement,
                "metric": item.get("metric"),
                "value": item.get("value"),
                "unit": item.get("unit"),
                "type": item.get("type") or "dataset_fact",
                "source": "computed",
            }
        )

    # Keep newest focus first, then unique later bullets from history.
    seen = {bullets[0].lower()} if bullets else set()
    for bullet in prior_bullets:
        key = bullet.lower()
        if key in seen:
            continue
        # Drop stale Focus lines; newest focus already added.
        if bullet.lower().startswith("focus:"):
            continue
        seen.add(key)
        bullets.append(bullet)
        if len(bullets) >= MAX_WORKING_BULLETS:
            break
    bullets = bullets[:MAX_WORKING_BULLETS]

    deduped_decisions: List[Dict[str, Any]] = []
    seen_statements: set[str] = set()
    for item in reversed(decisions):
        statement = str(item.get("statement") or "").strip()
        key = statement.lower()
        if not statement or key in seen_statements:
            continue
        seen_statements.add(key)
        deduped_decisions.append(item)
        if len(deduped_decisions) >= MAX_DECISIONS:
            break
    deduped_decisions.reverse()

    summary_text = "\n".join(f"- {bullet}" for bullet in bullets)
    if len(summary_text) > MAX_SUMMARY_CHARS:
        summary_text = summary_text[: MAX_SUMMARY_CHARS - 1].rstrip() + "…"

    compact_facts = [
        {
            key: item.get(key)
            for key in (
                "id",
                "type",
                "metric",
                "value",
                "unit",
                "evidence",
                "provenance",
                "eligibility",
            )
            if isinstance(item, dict) and item.get(key) is not None
        }
        for item in facts
        if isinstance(item, dict)
    ]
    facts_hash = (
        hashlib.sha256(
            json.dumps(compact_facts, ensure_ascii=False, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        if compact_facts
        else previous_value.get("facts_hash")
    )
    value = {
        "conversation_id": conversation_id or previous_value.get("conversation_id"),
        "bullets": bullets,
        "decisions": deduped_decisions,
        "computed_facts": compact_facts or previous_value.get("computed_facts") or [],
        "facts_hash": facts_hash,
        "summary_text": summary_text,
        "source_question": focus[:500],
    }
    return summary_text, value


def _score_memory_rows(question: str, rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    adapted = []
    for row in rows:
        value = row.get("value") if isinstance(row.get("value"), dict) else {}
        adapted.append(
            {
                **row,
                "question": row.get("summary") or "",
                "insight": json.dumps(value, ensure_ascii=False, default=str)[:1200],
                "keywords": row.get("keywords") or extract_keywords(
                    f"{row.get('summary') or ''} {value.get('source_question') or ''}",
                    limit=24,
                ),
            }
        )
    ranked = rank_memories(question, adapted, limit=limit)
    if ranked:
        return ranked
    return rows[:limit]


def fetch_chat_memory(
    user_id: str,
    conversation_id: Optional[str],
    dataset_key: Optional[str] = None,
    question: str = "",
) -> Dict[str, Any]:
    if not user_id:
        return {}
    try:
        client = get_supabase_client()
        memory_keys = ["preferences"]
        if conversation_id:
            memory_keys.append(conversation_id)
        if dataset_key:
            memory_keys.append(dataset_key)

        keyed = (
            client.table("chat_memories")
            .select("scope,summary,value,updated_at,keywords,memory_key")
            .eq("user_id", user_id)
            .in_("memory_key", memory_keys)
            .order("updated_at", desc=True)
            .limit(20)
            .execute()
        )
        rows = list(keyed.data or [])

        # Rank additional project memories against the current question.
        if question.strip():
            project_rows = (
                client.table("chat_memories")
                .select("scope,summary,value,updated_at,keywords,memory_key")
                .eq("user_id", user_id)
                .eq("scope", "project")
                .order("updated_at", desc=True)
                .limit(24)
                .execute()
            ).data or []
            for row in _score_memory_rows(question, project_rows, limit=4):
                if row.get("memory_key") not in memory_keys:
                    rows.append(row)

        result: Dict[str, Any] = {}
        scoped_candidates: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            scope = row.get("scope")
            value = row.get("value") or {}
            row_conversation = value.get("conversation_id")
            if scope in {"conversation", "evidence"} and conversation_id:
                if row.get("memory_key") != conversation_id:
                    continue
                if row_conversation and row_conversation != conversation_id:
                    continue
            scoped_candidates.setdefault(scope, []).append(row)

        for scope, candidates in scoped_candidates.items():
            if scope == "project" and question.strip() and len(candidates) > 1:
                chosen_rows = _score_memory_rows(question, candidates, limit=1)
            else:
                chosen_rows = candidates[:1]
            if not chosen_rows:
                continue
            chosen = chosen_rows[0]
            result[scope] = {
                "summary": chosen.get("summary") or "",
                "value": chosen.get("value") or {},
            }

        try:
            from app.services.governed_memory import retrieve_governed_memory

            governed = retrieve_governed_memory(
                user_id,
                question,
                dataset_key=dataset_key,
                limit=8,
                max_chars=5000,
            )
            if governed.get("items"):
                result["governed"] = governed
        except Exception as governed_exc:
            print(f"fetch governed memory failed: {governed_exc}")
        return result
    except Exception as exc:
        print(f"fetch_chat_memory failed: {exc}")
        return {}


def _load_memory_row(
    client: Any,
    user_id: str,
    scope: str,
    memory_key: str,
) -> Dict[str, Any]:
    response = (
        client.table("chat_memories")
        .select("summary,value,keywords")
        .eq("user_id", user_id)
        .eq("scope", scope)
        .eq("memory_key", memory_key)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else {}


def save_chat_memory(
    user_id: str,
    conversation_id: Optional[str],
    question: str,
    answer: str,
    *,
    web_sources: Optional[List[Dict[str, Any]]] = None,
    dataset_key: Optional[str] = None,
    computed_facts: Optional[List[Dict[str, Any]]] = None,
) -> None:
    del answer  # Never persist generated answer prose as memory.
    if not user_id:
        return
    try:
        client = get_supabase_client()
        existing_prefs = _load_memory_row(client, user_id, "user", "preferences")
        prefs = merge_user_preferences(
            existing_prefs.get("value") if isinstance(existing_prefs.get("value"), dict) else {},
            infer_user_preferences(question),
        )
        client.table("chat_memories").upsert(
            {
                "user_id": user_id,
                "scope": "user",
                "memory_key": "preferences",
                "summary": "Display and analysis preferences",
                "value": prefs,
                "keywords": [str(v) for v in prefs.values() if v is not None],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="user_id,scope,memory_key",
        ).execute()

        facts = [
            {
                key: item.get(key)
                for key in (
                    "id",
                    "type",
                    "metric",
                    "value",
                    "unit",
                    "evidence",
                    "provenance",
                    "eligibility",
                )
                if item.get(key) is not None
            }
            for item in list(computed_facts or [])[:24]
            if isinstance(item, dict)
        ]
        facts_hash = (
            hashlib.sha256(
                json.dumps(facts, ensure_ascii=False, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            if facts
            else None
        )

        if conversation_id:
            existing_conversation = _load_memory_row(
                client, user_id, "conversation", conversation_id
            )
            summary, value = build_rolling_conversation_memory(
                question=question,
                conversation_id=conversation_id,
                previous_summary=existing_conversation.get("summary") or "",
                previous_value=(
                    existing_conversation.get("value")
                    if isinstance(existing_conversation.get("value"), dict)
                    else {}
                ),
                computed_facts=facts,
            )
            client.table("chat_memories").upsert(
                {
                    "user_id": user_id,
                    "scope": "conversation",
                    "memory_key": conversation_id,
                    "summary": summary,
                    "value": value,
                    "keywords": extract_keywords(summary),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="user_id,scope,memory_key",
            ).execute()
            if web_sources:
                client.table("chat_memories").upsert(
                    {
                        "user_id": user_id,
                        "scope": "evidence",
                        "memory_key": conversation_id,
                        "summary": "Web evidence used in recent answers",
                        "value": {
                            "conversation_id": conversation_id,
                            "sources": web_sources[:12],
                        },
                        "keywords": extract_keywords(
                            " ".join(source.get("title", "") for source in web_sources)
                        ),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    on_conflict="user_id,scope,memory_key",
                ).execute()

        if dataset_key and facts:
            fact_labels = ", ".join(
                f"{item.get('metric')}={item.get('value')} {item.get('unit', '')}".strip()
                for item in facts[:8]
            )
            project_summary = f"Verified computed facts: {fact_labels}"[:1800]
            client.table("chat_memories").upsert(
                {
                    "user_id": user_id,
                    "scope": "project",
                    "memory_key": dataset_key,
                    "summary": project_summary,
                    "value": {
                        "dataset_key": dataset_key,
                        "computed_facts": facts,
                        "facts_hash": facts_hash,
                        "source_question": question[:500],
                    },
                    "keywords": extract_keywords(project_summary),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="user_id,scope,memory_key",
            ).execute()
    except Exception as exc:
        print(f"save_chat_memory failed: {exc}")


def get_user_analysis_preferences(user_id: str) -> Dict[str, Any]:
    if not user_id:
        return {}
    try:
        row = _load_memory_row(get_supabase_client(), user_id, "user", "preferences")
        value = row.get("value") if isinstance(row.get("value"), dict) else {}
        return {
            "language": value.get("language") or "",
            "answer_style": value.get("answer_style") or "",
            "currency": value.get("currency") or "",
            "value": value,
            "updated_at": row.get("updated_at"),
        }
    except Exception as exc:
        print(f"get_user_analysis_preferences failed: {exc}")
        return {}


def save_user_analysis_preferences(user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    if not user_id:
        raise ValueError("user_id is required")
    allowed: Dict[str, Any] = {}
    if "language" in updates:
        language = str(updates.get("language") or "").strip().lower()
        if language in {"", "auto"}:
            allowed["language"] = None
        elif language in {"th", "en"}:
            allowed["language"] = language
        else:
            raise ValueError("Invalid language preference")
    if "answer_style" in updates:
        style = str(updates.get("answer_style") or "").strip().lower()
        if style in {"", "auto", "balanced"}:
            allowed["answer_style"] = None
        elif style in {"concise", "detailed"}:
            allowed["answer_style"] = style
        else:
            raise ValueError("Invalid answer style preference")
    if "currency" in updates:
        currency = str(updates.get("currency") or "").strip().upper()
        if currency in {"", "AUTO"}:
            allowed["currency"] = None
        elif re.fullmatch(r"[A-Z]{3}", currency or ""):
            allowed["currency"] = currency
        else:
            raise ValueError("Invalid currency preference")

    client = get_supabase_client()
    existing = _load_memory_row(client, user_id, "user", "preferences")
    current = existing.get("value") if isinstance(existing.get("value"), dict) else {}
    merged = dict(current)
    for key, value in allowed.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    client.table("chat_memories").upsert(
        {
            "user_id": user_id,
            "scope": "user",
            "memory_key": "preferences",
            "summary": "Display and analysis preferences",
            "value": merged,
            "keywords": [str(v) for v in merged.values() if v is not None],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id,scope,memory_key",
    ).execute()
    return get_user_analysis_preferences(user_id)


def record_chat_quality_event(
    user_id: str,
    conversation_id: Optional[str],
    event_type: str,
    payload: Dict[str, Any],
) -> None:
    if not user_id:
        return
    try:
        get_supabase_client().table("chat_quality_events").insert(
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "event_type": event_type,
                "payload": payload or {},
            }
        ).execute()
    except Exception as exc:
        print(f"record_chat_quality_event failed: {exc}")
