"""Server-owned tool execution contract for analytical chat.

The LLM may choose or plan tools, but only server-executed tools are allowed to
produce quantitative evidence.  This module keeps that boundary explicit and
provides the final fail-closed guard used by both streaming and non-streaming
responses.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _stable_id(prefix: str, value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def calculator_finding(tool_result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Convert a safe-calculator result into verifier-compatible evidence."""
    if not tool_result or tool_result.get("result") is None:
        return None
    value = tool_result["result"]
    expression = str(tool_result.get("expression") or "calculation")
    identity = {"engine": "safe_calculator", "expression": expression, "value": value}
    return {
        "id": _stable_id("f", identity),
        "type": "calculator_result",
        "metric": expression,
        "value": value,
        "unit": "",
        "direction": "neutral",
        "significance": "deterministic",
        "evidence": str(tool_result.get("formatted") or f"Calculator result: {value}"),
        "interpretation": "",
        "suggested_action": "",
        "provenance": {
            "engine": "safe_calculator",
            "source_columns": [],
            "query_hash": _stable_id("q", expression),
            "result_hash": _stable_id("r", value),
            "row_count": None,
            "period": None,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        },
        "eligibility": {"eligible": True},
        "audit": {
            "sql": None,
            "formula": expression,
            "filters": [],
            "metric_definition": None,
            "details": {"server_executed": True},
        },
    }


def calculator_findings(tool_result: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return result plus literal inputs so narration can quote the full expression."""
    result_finding = calculator_finding(tool_result)
    if result_finding is None:
        return []
    findings = [result_finding]
    expression = str((tool_result or {}).get("expression") or "")
    result_value = (tool_result or {}).get("result")
    for index, raw in enumerate(re.findall(r"-?\d[\d,]*(?:\.\d+)?", expression), 1):
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if isinstance(result_value, (int, float)) and value == float(result_value):
            continue
        value = int(value) if value.is_integer() else value
        identity = {"engine": "safe_calculator", "expression": expression, "input": value}
        findings.append({
            **result_finding,
            "id": _stable_id("f", identity),
            "type": "calculator_input",
            "metric": f"calculator_input_{index}",
            "value": value,
            "evidence": f"Literal input from the user expression: {raw}",
            "provenance": {
                **result_finding["provenance"],
                "result_hash": _stable_id("r", value),
            },
        })
    return findings


def _dataset_call(analytics_results: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    analytics = analytics_results or {}
    question_result = analytics.get("question_aware") or {}
    findings = analytics.get("structured_findings") or []
    success = bool(analytics) and question_result.get("success", True) is not False
    return {
        "id": _stable_id(
            "tool",
            {
                "name": "dataset_query",
                "engine": question_result.get("engine") or "duckdb",
                "code": question_result.get("code") or "base_analytics",
            },
        ),
        "tool": "dataset_query",
        "engine": question_result.get("engine") or "duckdb",
        "status": "completed" if success else "failed",
        "server_executed": True,
        "numeric_evidence": bool(findings),
        "evidence_ids": [item.get("id") for item in findings if item.get("id")],
        "error": question_result.get("error") if not success else None,
    }


def _typed_agent_calls(analytics_results: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    analytics = analytics_results or {}
    findings = analytics.get("structured_findings") or []
    calls: List[Dict[str, Any]] = []
    for record in analytics.get("agent_tool_calls") or []:
        tool_id = str(record.get("tool_id") or "")
        if not tool_id:
            continue
        evidence_ids = [
            item.get("id")
            for item in findings
            if item.get("id") and str(item.get("type") or "") == f"agent_{tool_id}"
        ]
        raw_status = str(record.get("status") or "failed")
        output_summary = record.get("output_summary") or {}
        semantic_success = output_summary.get("success", True) is not False
        status = "completed" if raw_status in {"completed", "cached"} and semantic_success else "failed"
        calls.append({
            "id": record.get("call_id") or _stable_id("tool", record),
            "tool": tool_id,
            "engine": output_summary.get("engine") or f"agent_tool_registry.{tool_id}",
            "status": status,
            "server_executed": True,
            "numeric_evidence": bool(evidence_ids),
            "evidence_ids": evidence_ids,
            "attempts": record.get("attempts"),
            "duration_ms": record.get("duration_ms"),
            "error": (
                record.get("error_code") or record.get("error") or output_summary.get("reason")
                if status == "failed" else None
            ),
        })
    return calls


def build_tool_execution(
    intent: Dict[str, Any],
    *,
    analytics_results: Optional[Dict[str, Any]] = None,
    calculator_result: Optional[Dict[str, Any]] = None,
    web_result: Optional[Dict[str, Any]] = None,
    clock_result: Optional[Dict[str, Any]] = None,
    selected_tools: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build a UI ledger from model-selected tools (preferred) or dataset intent."""
    required: List[str] = []
    calls: List[Dict[str, Any]] = []
    model_selected = selected_tools is not None
    selected = [
        str(tool).strip()
        for tool in (selected_tools or [])
        if str(tool).strip()
    ]

    def _append_calculator() -> None:
        required.append("safe_calculator")
        calc_findings = calculator_findings(calculator_result)
        calls.append({
            "id": _stable_id(
                "tool",
                {
                    "name": "safe_calculator",
                    "expression": (calculator_result or {}).get("expression"),
                },
            ),
            "tool": "safe_calculator",
            "engine": "safe_calculator",
            "status": "completed" if calculator_result else "failed",
            "server_executed": True,
            "numeric_evidence": bool(calculator_result),
            "evidence_ids": [item["id"] for item in calc_findings],
            "error": None if calculator_result else "No safe arithmetic expression could be parsed.",
        })

    def _append_web() -> None:
        required.append("web_search")
        sources = (web_result or {}).get("web_sources") or []
        calls.append({
            "id": _stable_id(
                "tool",
                {"name": "web_search", "queries": (web_result or {}).get("queries") or []},
            ),
            "tool": "web_search",
            "engine": "server_web_search",
            "status": "completed" if sources else "failed",
            "server_executed": True,
            "numeric_evidence": bool(sources),
            "evidence_ids": [
                _stable_id("source", source.get("url") or source)
                for source in sources
            ],
            "source_count": len(sources),
            "error": None if sources else "No web evidence was returned.",
        })

    def _append_clock() -> None:
        required.append("server_clock")
        ok = bool((clock_result or {}).get("success") or (clock_result or {}).get("iso"))
        calls.append({
            "id": _stable_id("tool", {"name": "server_clock"}),
            "tool": "server_clock",
            "engine": "server_clock",
            "status": "completed" if ok else "failed",
            "server_executed": True,
            # Date/time from the server clock is authoritative evidence.
            "numeric_evidence": ok,
            "evidence_ids": [_stable_id("clock", (clock_result or {}).get("iso") or "")] if ok else [],
            "error": None if ok else "Server clock was not returned.",
        })

    if model_selected:
        # Model-chosen tools only — never invent requirements from keyword intent.
        for tool_id in selected:
            if tool_id in {"safe_calculator", "calculator"} and "safe_calculator" not in required:
                _append_calculator()
            elif tool_id == "web_search" and "web_search" not in required:
                _append_web()
            elif tool_id in {"server_clock", "clock"} and "server_clock" not in required:
                _append_clock()
            elif tool_id in {"query_data", "dataset_query"} and "dataset_query" not in required:
                required.append("dataset_query")
                calls.append(_dataset_call(analytics_results))
                calls.extend(_typed_agent_calls(analytics_results))
    else:
        if intent.get("needs_dataset"):
            required.append("dataset_query")
            calls.append(_dataset_call(analytics_results))
            calls.extend(_typed_agent_calls(analytics_results))

        # Legacy keyword path — calculator only for explicit arithmetic, not weather/FX.
        if intent.get("needs_calculator") and not intent.get("needs_dataset"):
            _append_calculator()

        if intent.get("needs_web"):
            _append_web()

    completed = {call["tool"] for call in calls if call["status"] == "completed"}
    missing = [tool for tool in required if tool not in completed]
    return {
        "version": "tool_execution_v1",
        "policy": "model_selected_tools" if model_selected else "tool_first_compute_only",
        "required": required,
        "satisfied": not missing,
        "missing": missing,
        "numeric_evidence_available": any(
            call.get("status") == "completed" and call.get("numeric_evidence")
            for call in calls
        ),
        # Clock/web/calc completions count as tool evidence even without KPI numbers.
        "tool_evidence_available": bool(completed),
        "calls": calls,
    }


def tool_gate_message(tool_execution: Optional[Dict[str, Any]], *, thai: bool) -> Optional[str]:
    """Return a deterministic response when a required analytical tool failed."""
    execution = tool_execution or {}
    if execution.get("satisfied", True):
        return None
    missing = [str(item) for item in (execution.get("missing") or [])]
    # Web-only miss: let the model explain that sources were empty; number scrub still applies.
    if set(missing) == {"web_search"}:
        if thai:
            return (
                "ค้นข้อมูลภายนอกแล้วแต่ยังไม่มีแหล่งที่ใช้งานได้ "
                "จึงยังสรุปตัวเลขสด (เรท/ราคา/อากาศ ฯลฯ) ไม่ได้ "
                "ระบบจะไม่ให้ AI เดาแทน — ลองถามใหม่หรือระบุคู่สกุลเงินให้ชัดขึ้น"
            )
        return (
            "External search ran but returned no usable sources, so live figures "
            "(rates/prices/weather, etc.) cannot be stated. The AI will not invent them — "
            "try again or name the currency pair more clearly."
        )
    missing_text = ", ".join(missing)
    if thai:
        return (
            "ยังสรุปผลเชิงตัวเลขไม่ได้ เพราะเครื่องมือที่จำเป็นทำงานไม่สำเร็จ "
            f"({missing_text}) ระบบจะไม่ให้ AI คำนวณหรือเดาตัวเลขแทนเครื่องมือ"
        )
    return (
        "I cannot provide a quantitative result because the required tool did not "
        f"complete ({missing_text}). The AI will not calculate or guess a replacement value."
    )


def enforce_tool_grounding(
    answer: str,
    verification: Dict[str, Any],
    *,
    thai: bool,
) -> tuple[str, Dict[str, Any]]:
    """Remove unsupported quantitative lines after correction attempts.

    The guard is intentionally fail-closed: an unverified number never reaches
    the final answer even if the verifier or correction model could not repair it.
    """
    evidence_scope_active = bool(
        verification.get("evidence_scope_active")
        or verification.get("evidence_count", 0) > 0
        or verification.get("finding_count", 0) > 0
    )
    if not evidence_scope_active:
        return answer, {
            "applied": False,
            "removed_claims": [],
            "reason": "no_tool_evidence",
        }
    if any(
        "verification was unavailable" in str(warning).lower()
        for warning in verification.get("warnings") or []
    ):
        notice = (
            "ไม่สามารถยืนยันหลักฐานเชิงตัวเลขได้ในครั้งนี้ ระบบจึงไม่ส่งคำตอบจากโมเดล"
            if thai
            else "Numeric evidence could not be verified, so the model-generated answer was withheld."
        )
        return notice, {
            "applied": True,
            "removed_claims": [],
            "removed_lines": len((answer or "").splitlines()),
            "reason": "verifier_unavailable",
        }
    unmatched = [
        str(item).strip()
        for item in verification.get("unmatched_dataset_numeric_claims") or []
        if str(item).strip()
    ]
    if not unmatched:
        return answer, {"applied": False, "removed_claims": []}

    patterns = [re.compile(re.escape(item), re.IGNORECASE) for item in unmatched]
    scrubbed_answer = re.sub(
        r"```[\s\S]*?```",
        lambda match: "" if any(pattern.search(match.group(0)) for pattern in patterns) else match.group(0),
        answer or "",
    )
    kept: List[str] = []
    removed_lines = 0
    for line in scrubbed_answer.splitlines():
        if any(pattern.search(line) for pattern in patterns):
            removed_lines += 1
            continue
        kept.append(line)
    safe_text = "\n".join(kept).strip()
    notice = (
        "> ระบบตัดข้อความที่มีตัวเลขซึ่งไม่ตรงกับหลักฐานจากเครื่องมือออกแล้ว"
        if thai
        else "> Statements containing numbers not supported by tool evidence were removed."
    )
    safe_text = "\n\n".join(part for part in [safe_text, notice] if part)
    return safe_text, {
        "applied": True,
        "removed_claims": unmatched,
        "removed_lines": removed_lines,
    }
