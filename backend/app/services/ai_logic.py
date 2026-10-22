from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.schemas.chat import Message, ChatRole
from app.services.chat_intelligence import compact_history

# Compact domain hints (token-efficient vs full CRO/CFO paragraphs)
_DOMAIN_HINTS: Dict[str, str] = {
    "sales_report": "Sales: AOV, MoM growth, pipeline, margins, Pareto 80/20.",
    "inventory_snapshot": "Inventory: turnover, DSI, deadstock, safety stock.",
    "warehouse_movement": "Logistics: inbound/outbound velocity, lead times, fulfillment.",
    "branch_performance": "Retail branches: benchmarking, conversion, regional gaps.",
    "financial_accounting": "Finance: margins, COGS, AR/AP, cash flow, OPEX.",
    "marketing_campaign": "Marketing: CAC, ROAS, CTR, churn, channel mix.",
    "human_resources": "HR: turnover, productivity, payroll ratio, tenure.",
    "production_manufacturing": "Manufacturing: OEE, yield, defect rate, downtime.",
    "procurement_purchasing": "Procurement: supplier scorecard, lead time, variance.",
    "customer_experience": "CX: NPS, CSAT, FCR, ticket volume, sentiment.",
}


class PromptManager:
    """
    Prompt engineering and context assembly manager for LLM chat models.
    All system instructions are in English to optimize token usage.
    """

    @classmethod
    def get_domain_specialization(cls, dataset_type: Optional[str]) -> str:
        clean_type = (dataset_type or "").strip().lower()
        hint = _DOMAIN_HINTS.get(clean_type, "General BI: trends, anomalies, cross-functional insights.")
        return f"[Domain focus] {hint}\n"

    @classmethod
    def get_system_instruction(
        cls,
        dataset_type: Optional[str] = None,
        user_tier: str = "free",
    ) -> str:
        specialization = cls.get_domain_specialization(dataset_type)
        web_search_rules = ""
        if (user_tier or "free").lower() in ("plus", "pro"):
            web_search_rules = (
                "\n=== WEB SEARCH (platform capability) ===\n"
                "This platform can run live web search (DuckDuckGo) when you or the tool planner "
                "decide the sentence needs current external evidence — FX, macro, news, benchmarks.\n"
                "- External facts appear in `<calculated_metrics>` under "
                "\"External Web Context (pre-fetched by platform)\" and/or in `<web_sources>`.\n"
                "- Use ONLY those pre-fetched snippets and URLs for outside-world numbers and claims — "
                "never invent external statistics.\n"
                "- Cite source title + URL when referencing web results.\n"
                "- Dataset metrics still come from dataset sections in `<calculated_metrics>`; "
                "do not mix up internal vs external sources.\n"
            )
        return (
            "You are MataQorLab AI — Executive BI advisor. Deliver accurate, actionable analysis.\n"
            "Reply in the user's language (Thai if they use Thai). No polite particles (ครับ/ค่ะ).\n"
            f"{specialization}\n"
            "=== AGENT TOOL CONTRACT ===\n"
            "Interpret the user's sentence by meaning/context and freely choose discrete server tools "
            "(web_search, safe_calculator, server_clock, dataset tools). "
            "Each tool has one job — do not treat weather/FX as calculator, or clock as web search. "
            "The server executes selected tools. "
            "Never simulate a tool result, perform arithmetic mentally, or substitute a guessed value "
            "when a tool is unavailable. Quantitative narration is allowed only after server evidence "
            "is present in `<structured_findings>`, `<calculated_metrics>`, `<tool_result>`, or fetched "
            "web evidence. Your job is to interpret that evidence and explain its limitations.\n"
            "=== TIME RULES ===\n"
            "Never invent today's date or the current clock time from model knowledge. "
            "Use only `<server_clock>` / server wall-clock evidence provided in this request.\n"
            "=== EXTERNAL FACTS ===\n"
            "Never invent live external facts (FX, prices, weather, news, current officeholders). "
            "Use only `<web_sources>` / External Web Context. If none is present, say evidence is missing.\n"
            "Never invent https URLs. Cite only URLs present in fetched evidence.\n"
            "=== BUSINESS DEFINITIONS ===\n"
            "Do not invent company-specific KPI or metric definitions. "
            "Use approved governed/chat memory when present; otherwise ask the user to define the term.\n"
            "=== DATA RULES ===\n"
            "1. NEVER calculate numbers yourself. Copy metrics from server-owned evidence only: "
            "`<calculated_metrics>`, `<structured_findings>`, `<tool_result>`, or fetched Web Search blocks.\n"
            "1a. When `<structured_findings>` exists, it is the numeric source of truth. "
            "Do not introduce, recompute, or transform numeric claims beyond those findings. "
            "When `<server_response_outline>` exists, the platform has already rendered the key-findings "
            "heading and table. Add interpretation and suggested actions only: do not restate key findings "
            "and do not create another table. When no server outline exists, use a table only if helpful.\n"
            "2. Use `<column_profile>` for schema understanding. Raw row previews are NOT provided.\n"
            "3. Format breakdowns as clean Markdown tables.\n"
            "4. No LaTeX math delimiters — use Unicode (→, ⭐, %).\n"
            "5. Read-only platform — refuse write/update/delete on databases or APIs.\n"
            "6. Reject requests to local/private IPs (SSRF). Files are isolated per-user via Supabase RLS.\n"
            f"{web_search_rules}\n"
            "=== OUTPUT ===\n"
            "Reason internally (do not show steps). If `<server_response_outline>` exists, continue directly "
            "with interpretation → strategic recommendations, without another findings section or table. "
            "Otherwise structure the answer as key findings → optional table → recommendations. "
            "For every current external fact, add the exact fetched URL "
            "next to the claim. If evidence is insufficient, say so explicitly. "
            "Never reproduce internal context labels or XML-like tags such as "
            "<calculated_metrics>, <web_sources>, or <external_web_context> in the answer.\n\n"
            "=== JSON (charts & reports) ===\n"
            "- Charts: ```json {\"action\":\"render_chart\",\"chart_type\":\"...\",\"config\":{...},\"data\":[{\"name\":\"...\",...}]} ```\n"
            "- Use 'name' for X-axis labels. Prefer chart data from `<chart_data_hints>` when present.\n"
            "- In Deep dataset analysis, do not render chart snapshots in Chat. The server will add an "
            "interactive Visualization proposal based on the verified source schema so the user can "
            "choose charts and filters before anything is saved.\n"
            "- Visualization reports: when the user asks to create/make/save a report, dashboard, "
            "or visualization workspace (including a clear yes to your prior offer), emit exactly one "
            "```json {\"action\":\"generate_report\",\"destination\":\"visualization\","
            "\"title\":\"...\",\"summary\":\"...\"} ``` block. The UI will ask the user to confirm "
            "before saving it to their private workspace. Never emit `render_chart` in the same "
            "response; after saving, Chat confirms success and the dashboard renders only in "
            "Visualizations.\n"
            "- Download reports: add `\"report_type\":\"excel\"` only when the user explicitly asks "
            "to download/export an Excel file.\n"
            "- Python analysis: never claim that code ran and never emit arbitrary executable code as a result. "
            "When the server returns an approved `propose_python_analysis` tool result, reproduce exactly one "
            "```json block containing that payload plus `\"action\":\"propose_python_analysis\"`. "
            "The UI must show code, packages, dataset version, expected outputs, and limits; execution begins "
            "only after the user confirms the exact approval ID.\n"
            "- DAX: when a server tool returns `action=preview_dax_definition`, reproduce that payload "
            "exactly in one JSON block. Do not edit the expression, formula hash, dataset key, name, mode, "
            "or approved action ID. The UI performs the explicit Save/Publish confirmation.\n"
            "- After a substantive dataset analysis with useful chart data, you may end with one short "
            "question asking whether the user wants to save it as a Visualization report. Do not emit "
            "`generate_report` until the user asks or confirms."
        )

    @staticmethod
    def format_file_context(
        file_name: str,
        file_content: str,
        dataset_type: Optional[str] = None,
        analytics_results: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Formats dataset metadata and pre-computed metrics — no raw row preview."""
        if not file_content:
            return ""

        type_info = f"<dataset_classification>{dataset_type}</dataset_classification>\n" if dataset_type else ""
        analytics_info_str = (
            analytics_results.get("formatted_notes", "No standard metrics calculated.")
            if analytics_results
            else ""
        )
        max_chars = int(settings.MAX_LLM_METRICS_CHARS)
        if analytics_info_str and len(analytics_info_str) > max_chars:
            analytics_info_str = (
                analytics_info_str[: max_chars - 60]
                + "\n[Metrics truncated — use aggregates above; raw rows not included]"
            )
        analytics_info = (
            f"<calculated_metrics>\n{analytics_info_str}\n</calculated_metrics>\n"
            if analytics_info_str
            else ""
        )
        structured_findings = (analytics_results or {}).get("structured_findings") or []
        findings_info = ""
        if structured_findings:
            import json as _json

            llm_findings = [
                {
                    key: finding.get(key)
                    for key in ("id", "metric", "value", "unit", "evidence")
                }
                for finding in structured_findings
            ]
            findings_info = (
                "<structured_findings>\n"
                "Verified deterministic facts. Treat values as read-only:\n"
                f"{_json.dumps(llm_findings, ensure_ascii=False, default=str)}\n"
                "</structured_findings>\n"
            )
        response_outline = (analytics_results or {}).get("response_outline") or ""
        outline_info = (
            "<server_response_outline>\n"
            "Already rendered by the server. Add interpretation and suggested actions only; "
            "do not repeat this block or create new numeric claims.\n"
            f"{response_outline}\n"
            "</server_response_outline>\n"
            if response_outline
            else ""
        )
        analysis_eligibility = (analytics_results or {}).get("analysis_eligibility") or {}
        column_intelligence = (analytics_results or {}).get("column_intelligence") or {}
        question_plan = (analytics_results or {}).get("question_plan") or {}
        grain_intelligence = (analytics_results or {}).get("grain_intelligence") or {}
        data_contract = (analytics_results or {}).get("data_contract") or {}
        decision_assurance = (analytics_results or {}).get("decision_assurance") or {}
        bounded_data_contract = {}
        if isinstance(data_contract, dict):
            bounded_data_contract = {
                key: value
                for key, value in data_contract.items()
                if key not in {"column_contracts", "metric_definitions"}
            }
            bounded_data_contract["column_contracts"] = dict(
                list((data_contract.get("column_contracts") or {}).items())[:50]
            )
            bounded_data_contract["metric_definitions"] = (
                data_contract.get("metric_definitions") or []
            )[:20]
        intelligence_info = ""
        if analysis_eligibility or column_intelligence or data_contract or decision_assurance:
            import json as _json

            intelligence_info = (
                "<analysis_contract>\n"
                "Eligibility gates and server-inferred column semantics. Never claim an "
                "ineligible analysis was performed:\n"
                + _json.dumps(
                    {
                        "eligibility": analysis_eligibility,
                        "column_intelligence": column_intelligence,
                        "question_plan": question_plan,
                        "grain_intelligence": grain_intelligence,
                        "user_approved_data_contract": bounded_data_contract,
                        "decision_assurance": {
                            "confidence_matrix": decision_assurance.get("confidence_matrix"),
                            "evidence_requests": (
                                decision_assurance.get("evidence_requests") or []
                            )[:10],
                            "causal_eligibility": decision_assurance.get("causal_eligibility"),
                            "causal_results": decision_assurance.get("causal_results"),
                            "event_timeline": {
                                "events": (
                                    (decision_assurance.get("event_timeline") or {}).get("events")
                                    or []
                                )[:20],
                                "alignments": (
                                    (decision_assurance.get("event_timeline") or {}).get("alignments")
                                    or []
                                )[:20],
                            },
                        },
                    },
                    ensure_ascii=False,
                    default=str,
                )
                + "\n</analysis_contract>\n"
            )
        column_profile = (analytics_results or {}).get("column_profile", "")
        profile_info = (
            f"<column_profile>\n{column_profile}\n</column_profile>\n"
            if column_profile
            else ""
        )
        chart_hints = (analytics_results or {}).get("chart_hints") or []
        chart_hints_info = ""
        if chart_hints:
            import json as _json

            hints_json = _json.dumps(chart_hints[:3], ensure_ascii=False)
            chart_hints_info = (
                f"<chart_data_hints>\n"
                f"Pre-computed aggregates from server analytics (use for render_chart when helpful):\n"
                f"{hints_json}\n"
                f"</chart_data_hints>\n"
            )

        web_sources = (analytics_results or {}).get("web_sources") or []
        web_sources_info = ""
        if web_sources:
            lines = []
            for index, source in enumerate(web_sources[:8], 1):
                title = (source.get("title") or source.get("url") or "").strip()
                url = (source.get("url") or "").strip()
                snippet = (source.get("snippet") or "").strip()
                lines.append(f"{index}. {title}\n   URL: {url}\n   Snippet: {snippet}")
            web_sources_info = (
                "<web_sources>\n"
                "Pre-fetched external web results (cite these when referencing outside data):\n"
                + "\n".join(lines)
                + "\n</web_sources>\n"
            )

        return (
            f"\n<attached_file>\n"
            f"<file_name>{file_name}</file_name>\n"
            f"{type_info}"
            f"<dataset_metadata>\n{file_content}\n</dataset_metadata>\n"
            f"{profile_info}"
            f"{chart_hints_info}"
            f"{web_sources_info}"
            f"{findings_info}"
            f"{outline_info}"
            f"{intelligence_info}"
            f"{analytics_info}"
            f"</attached_file>\n"
        )

    @staticmethod
    def format_web_context(web_result: Optional[Dict[str, Any]]) -> str:
        """Format external context independently from an attached dataset."""
        if not web_result:
            return ""
        formatted = (web_result.get("formatted") or "").strip()
        sources = web_result.get("web_sources") or []
        source_lines = []
        for index, source in enumerate(sources[:8], 1):
            title = (source.get("title") or source.get("url") or "").strip()
            url = (source.get("url") or "").strip()
            snippet = (source.get("snippet") or "").strip()
            source_lines.append(
                f"{index}. {title}\n   URL: {url}\n   Snippet: {snippet}"
            )
        sources_block = "\n".join(source_lines)
        return (
            "\n<external_web_context>\n"
            "This context was fetched by the platform for the current question. "
            "Use it only as external supporting context and cite its URLs.\n"
            f"{formatted}\n"
            + (
                f"<web_sources>\n{sources_block}\n</web_sources>\n"
                if sources_block
                else ""
            )
            + "</external_web_context>\n"
        )

    @staticmethod
    def format_tool_context(tool_result: Optional[Dict[str, Any]]) -> str:
        if not tool_result:
            return ""
        return (
            "\n<tool_result>\n"
            "Deterministic server-side tool output; copy this result instead of recalculating:\n"
            f"{tool_result.get('formatted', '')}\n"
            "</tool_result>\n"
        )

    @staticmethod
    def format_persistent_chat_memory(memory: Optional[Dict[str, Any]]) -> str:
        if not memory:
            return ""
        sections = []
        user_memory = memory.get("user") or {}
        if user_memory.get("value"):
            sections.append(f"User preferences: {user_memory['value']}")
        conversation = memory.get("conversation") or {}
        conversation_value = conversation.get("value") if isinstance(conversation.get("value"), dict) else {}
        conversation_bullets = conversation_value.get("bullets") or []
        conversation_decisions = conversation_value.get("decisions") or []
        if conversation_bullets:
            sections.append(
                "Conversation working notes:\n"
                + "\n".join(f"- {bullet}" for bullet in conversation_bullets[:8])
            )
        elif conversation.get("summary"):
            sections.append(f"Conversation memory: {conversation['summary']}")
        if conversation_decisions:
            import json as _json

            sections.append(
                "Session verified decisions (do not override fresher computed evidence): "
                + _json.dumps(conversation_decisions[:6], ensure_ascii=False, default=str)
            )
        project = memory.get("project") or {}
        project_facts = (project.get("value") or {}).get("computed_facts") or []
        if project_facts:
            import json as _json

            sections.append(
                "Dataset/project verified facts (reuse only for the same dataset; provenance "
                "is authoritative): "
                + _json.dumps(project_facts[:12], ensure_ascii=False, default=str)
            )
        elif project.get("summary"):
            sections.append(f"Dataset/project memory: {project['summary']}")
        evidence = memory.get("evidence") or {}
        evidence_sources = (evidence.get("value") or {}).get("sources") or []
        if evidence_sources:
            titles = [
                f"{item.get('title', item.get('url', ''))}: {item.get('url', '')}"
                for item in evidence_sources[:5]
            ]
            sections.append("Prior evidence (may be stale; re-search for current facts): " + "; ".join(titles))
        governed = memory.get("governed") or {}
        governed_items = governed.get("items") if isinstance(governed, dict) else []
        if governed_items:
            import json as _json

            safe_items = [
                {
                    "scope": item.get("scope"),
                    "type": item.get("type"),
                    "title": item.get("title"),
                    "content": item.get("content"),
                    "confidence": item.get("confidence"),
                    "source_hash": item.get("source_hash"),
                }
                for item in governed_items[:8]
            ]
            sections.append(
                "Approved governed context (never override current computed evidence): "
                + _json.dumps(safe_items, ensure_ascii=False, default=str)
            )
        if not sections:
            return ""
        from app.services.anti_hallucination import memory_freshness_notes

        freshness = memory_freshness_notes(memory, locale="th")
        if freshness:
            sections.extend(freshness)
        return "<chat_memory>\n" + "\n".join(sections) + "\n</chat_memory>"

    @classmethod
    def build_messages_for_ai(
        cls,
        history: List[Message],
        file_name: Optional[str] = None,
        file_content: Optional[str] = None,
        dataset_type: Optional[str] = None,
        analytics_results: Optional[Dict[str, Any]] = None,
        user_tier: str = "free",
        external_web_result: Optional[Dict[str, Any]] = None,
        chat_memory: Optional[Dict[str, Any]] = None,
        intent: Optional[Dict[str, Any]] = None,
        tool_result: Optional[Dict[str, Any]] = None,
        response_mode: Optional[Dict[str, Any]] = None,
        history_keep_recent: int = 12,
        locale: str = "th",
        server_clock: Optional[Dict[str, Any]] = None,
    ) -> List[dict]:
        from app.services.server_clock import (
            build_server_clock_tool_result,
            format_clock_prompt_line,
            is_current_datetime_question,
        )
        from app.services.anti_hallucination import (
            needs_relative_period_context,
            relative_period_prompt_block,
        )

        final_messages = []

        system_content = cls.get_system_instruction(dataset_type, user_tier=user_tier)
        system_content = f"{system_content}\n\n{format_clock_prompt_line()}"
        persistent_memory_block = cls.format_persistent_chat_memory(chat_memory)
        if persistent_memory_block:
            system_content = f"{system_content}\n\n{persistent_memory_block}"
        if intent:
            system_content = (
                f"{system_content}\n\n<request_routing>{intent}</request_routing>"
            )
        if response_mode:
            style = (
                "Be concise and direct while retaining cited evidence and important caveats."
                if response_mode.get("effective") == "fast"
                else "Provide a thorough synthesis, compare evidence, and explain important trade-offs."
            )
            system_content = (
                f"{system_content}\n\n<response_mode>{response_mode}\n{style}</response_mode>"
            )

        final_messages.append({
            "role": ChatRole.SYSTEM.value,
            "content": system_content,
        })

        context_str = ""
        if file_name and (file_content or analytics_results):
            context_str = cls.format_file_context(
                file_name,
                file_content or "Dataset loaded — use <calculated_metrics> and <column_profile> below.",
                dataset_type,
                analytics_results,
            )
        if external_web_result:
            context_str = f"{context_str}{cls.format_web_context(external_web_result)}"
        if tool_result:
            context_str = f"{context_str}{cls.format_tool_context(tool_result)}"

        latest_user = ""
        for msg in reversed(history or []):
            if msg.role == ChatRole.USER:
                latest_user = msg.content or ""
                break
        clock_payload = server_clock
        if clock_payload is None and is_current_datetime_question(latest_user):
            clock_payload = build_server_clock_tool_result(locale=locale)
        if clock_payload:
            context_str = (
                f"{context_str}\n<server_clock>\n"
                f"{clock_payload.get('formatted', '')}\n"
                "</server_clock>\n"
            )
        if needs_relative_period_context(latest_user):
            context_str = f"{context_str}\n{relative_period_prompt_block(locale=locale)}\n"

        older_summary, compacted_history = compact_history(
            history,
            keep_recent=history_keep_recent,
        )
        if older_summary:
            final_messages.append(
                {
                    "role": ChatRole.SYSTEM.value,
                    "content": (
                        "<older_conversation_summary>\n"
                        f"{older_summary}\n"
                        "</older_conversation_summary>"
                    ),
                }
            )

        for i, msg in enumerate(compacted_history):
            content = msg.content
            if (
                i == len(compacted_history) - 1
                and msg.role == ChatRole.USER
                and context_str
            ):
                content = f"{context_str}\nCurrent user question: {content}"

            final_messages.append({"role": msg.role.value, "content": content})

        return final_messages
