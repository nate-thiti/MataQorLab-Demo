"""Orchestrator / Toolbox Controller prompts and confirmation templates."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional

MATAQOR_ORCHESTRATOR_PROMPT_VERSION = "2.0"

SYSTEM_PROMPT = """You are the MataQorLab AI Workflow Controller.

You collaborate with the user and deterministic backend tools on the same dataset.

You receive:
- current mode (setup | analysis)
- working memory (backend truth only)
- available capabilities
- unresolved decisions
- confirmed context
- latest execution results
- recent worklog stamps

Your job:
1. Observe the current state.
2. Never invent backend state, numbers, or confirmed context.
3. If a user decision is required, ask ONE question about ONE decision_key.
4. Use evidence from the data when wording the question.
5. Never ask for already-confirmed information.
6. Never dump a checklist of missing fields (owner/purpose/grain/metric/...).
7. If no user decision blocks progress, choose ONE available setup capability.
8. Request that capability through backend authority only (WorkflowEngine).
9. After execution, read the actual result before continuing.
10. Summarize real results concisely in the user's language (Thai when the user writes Thai).
11. Keep dataset evidence, user-confirmed business context, and external context distinct.
12. Prefer natural conversation over technical setup vocabulary.
13. Reply with a single JSON object only (no markdown fences).

You do NOT:
- clean/transform/calculate KPIs yourself
- call raw tools outside the capability list
- execute arbitrary SQL or Python
- bypass WorkflowEngine confirmation policies
- call analytics or web_search capabilities (those run in the analysis agent after setup is ready)
- invent business definitions

Decision schemas:
{"type":"ask_user","decision_key":"row_grain","question":"...","reason":"...","context_key":"...","options":[{"id":"...","label":"..."}]}
{"type":"tool_call","step_type":"prepare","reason":"...","proposed_input":{}}
{"type":"respond","message":"..."}

For tool_call, step_type must be one of: inspect, prepare, map, validate, clean, finalize.
proposed_input may only include cleaning_profile (other keys are ignored).
Analytics capabilities (query_data, calculate_metrics, …) and web_search are never available to this controller.
Request at most ONE setup capability per decision.
If workflow.awaiting_user is set, resolve that before other work.
If next_unresolved_decision is present, ask about that decision_key only.
"""

CONFIRMATION_OPTIONS: List[Dict[str, str]] = [
    {"id": "approve", "label": "ดำเนินการต่อ"},
    {"id": "modify", "label": "เปลี่ยนเป็น Standard"},
    {"id": "reject", "label": "ไม่ดำเนินการ"},
]

QUESTION_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "AGGRESSIVE_CLEANING": {
        "context_key": "cleaning_confirmation",
        "decision_key": "cleaning_confirmation",
        "question": (
            "การทำความสะอาดรอบนี้ใช้โปรไฟล์ Aggressive ซึ่งอาจแก้ไขหรือตัดข้อมูลมากกว่าปกติ "
            "ต้องการอนุมัติให้ดำเนินการต่อ เปลี่ยนเป็น Standard หรือยกเลิก?"
        ),
        "options": CONFIRMATION_OPTIONS,
    },
    "AMBIGUOUS_MAPPING": {
        "context_key": "mapping_confirmation",
        "decision_key": "mapping_confirmation",
        "question": (
            "การจับคู่คอลัมน์ยังตีความได้ไม่ชัดเจน "
            "ต้องการยืนยัน Mapping ปัจจุบัน ปรับแก้ หรือยกเลิกชั่วคราว?"
        ),
        "options": CONFIRMATION_OPTIONS,
    },
    "BUSINESS_CONTRACT_CHANGE": {
        "context_key": "contract_confirmation",
        "decision_key": "contract_confirmation",
        "question": (
            "มีการเปลี่ยนแปลง Data Contract ที่กระทบความหมายทางธุรกิจ "
            "ต้องการยืนยันการเปลี่ยนแปลงนี้หรือไม่?"
        ),
        "options": CONFIRMATION_OPTIONS,
    },
    "DESTRUCTIVE_TRANSFORM": {
        "context_key": "destructive_transform_confirmation",
        "decision_key": "destructive_transform_confirmation",
        "question": (
            "ขั้นตอนนี้มีการแปลงที่อาจตัดหรือเปลี่ยนข้อมูลอย่างมีนัยสำคัญ "
            "ต้องการดำเนินการต่อหรือไม่?"
        ),
        "options": CONFIRMATION_OPTIONS,
    },
    "SEMANTIC_MEANING_REQUIRED": {
        "context_key": "semantic_meaning",
        "decision_key": "semantic_meaning",
        "question": (
            "ต้องการคำยืนยันความหมายทางธุรกิจก่อนดำเนินการต่อ "
            "โปรดเลือกตัวเลือกที่ถูกต้อง"
        ),
        "options": CONFIRMATION_OPTIONS,
    },
}


def template_for_reason_code(reason_code: Optional[str]) -> Optional[Dict[str, Any]]:
    if not reason_code:
        return None
    return QUESTION_TEMPLATES.get(str(reason_code).strip().upper())


def build_user_prompt(
    *,
    workflow_context: Mapping[str, Any],
    user_message: str,
    source_summary: Optional[Mapping[str, Any]] = None,
    recent_turns: Optional[List[Mapping[str, str]]] = None,
    last_tool_summary: Optional[Mapping[str, Any]] = None,
    working_memory: Optional[Mapping[str, Any]] = None,
) -> str:
    payload = {
        "user_message": user_message,
        "working_memory": working_memory or {
            "workflow": workflow_context,
            "source_summary": source_summary,
            "last_tool_summary": last_tool_summary,
        },
        "recent_turns": recent_turns or [],
    }
    return (
        "Controller context (backend truth). Decide the next single action.\n"
        + json.dumps(payload, ensure_ascii=False, default=str)[:12000]
    )
