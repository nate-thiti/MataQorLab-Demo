import re
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from enum import Enum

class ChatRole(str, Enum): #
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class UserTier(str, Enum):
    FREE = "free"
    PLUS = "plus"
    PRO = "pro"

class TokenUsage(BaseModel):
    prompt_tokens: int = Field(..., description="จำนวน Token ที่ส่งเข้าไป")
    completion_tokens: int = Field(..., description="จำนวน Token ที่ตอบกลับมา")
    total_tokens: int = Field(..., description="รวมจำนวน Token ทั้งหมด")

_LATEX_SYMBOLS: list[tuple[str, str]] = [
    (r"\\rightarrow", "→"),
    (r"\\leftarrow", "←"),
    (r"\\Rightarrow", "⇒"),
    (r"\\Leftarrow", "⇐"),
    (r"\\leftrightarrow", "↔"),
    (r"\\div", "÷"),
    (r"\\times", "×"),
    (r"\\cdot", "·"),
    (r"\\pm", "±"),
    (r"\\approx", "≈"),
    (r"\\leq", "≤"),
    (r"\\geq", "≥"),
    (r"\\neq", "≠"),
    (r"\\star", "⭐"),
    (r"\\bullet", "•"),
    (r"\\sum", "Σ"),
    (r"\\infty", "∞"),
    (r"\\%", "%"),
    (r"\\percent", "%"),
    (r"\\left", ""),
    (r"\\right", ""),
    (r"\\,", " "),
    (r"\\;", " "),
    (r"\\:", " "),
    (r"\\quad", "  "),
    (r"\\qquad", "    "),
]

_FENCED_CODE_PATTERN = re.compile(r"(```[\s\S]*?```)")
_INTERNAL_CONTEXT_TAG_PATTERN = re.compile(
    r"</?(?:calculated_metrics|web_sources|external_web_context|attached_file|"
    r"column_profile|chart_data_hints|request_routing|response_mode|"
    r"older_conversation_summary|prior_analysis_memory|chat_memory|tool_result|"
    r"structured_findings|server_response_outline|analysis_contract)"
    r"(?:\s[^>]*)?>",
    re.IGNORECASE,
)
_INTERNAL_CONTEXT_LABEL_PATTERN = re.compile(
    r"^\s*(?:External Web Context\s*\([^)]*(?:platform|ระบบ)[^)]*\)|"
    r"บริบทจากเว็บภายนอก\s*\([^)]*\))\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _replace_latex_symbols(text: str) -> str:
    for pattern, replacement in _LATEX_SYMBOLS:
        text = re.sub(pattern, replacement, text)
    return text


def _convert_latex_inner(latex: str) -> str:
    text = latex.strip()

    for _ in range(20):
        match = re.search(
            r"\\frac\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
            text,
        )
        if not match:
            break
        numerator = _convert_latex_inner(match.group(1))
        denominator = _convert_latex_inner(match.group(2))
        replacement = f"({numerator}) / ({denominator})"
        text = text[: match.start()] + replacement + text[match.end() :]

    text = re.sub(
        r"\\(?:text|mathrm|textit|textrm|textbf)\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
        lambda m: _convert_latex_inner(m.group(1)),
        text,
    )

    def bold_repl(match: re.Match[str]) -> str:
        inner = _convert_latex_inner(match.group(1))
        return f"**{inner}**"

    text = re.sub(
        r"\\mathbf\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
        bold_repl,
        text,
    )

    text = re.sub(
        r"\\sqrt\{([^{}]*)\}",
        lambda m: f"√({_convert_latex_inner(m.group(1))})",
        text,
    )

    text = _replace_latex_symbols(text)
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    text = re.sub(r"\\.", "", text)
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"\s{2,}", " ", text).strip()


def _convert_math_delimiters(content: str) -> str:
    def block_repl(match: re.Match[str]) -> str:
        converted = _convert_latex_inner(match.group(1))
        if not converted:
            return ""
        return f"\n\n**{converted}**\n\n"

    content = re.sub(r"\$\$([\s\S]*?)\$\$", block_repl, content)
    content = re.sub(r"\\\[([\s\S]*?)\\\]", block_repl, content)

    def inline_repl(match: re.Match[str]) -> str:
        return _convert_latex_inner(match.group(1))

    content = re.sub(r"(?<!\$)\$(?!\$)([^$\n]+?)\$(?!\$)", inline_repl, content)
    content = re.sub(r"\\\(([^)]+?)\\\)", inline_repl, content)
    return content


def sanitize_message_content(content: str) -> str:
    """
    Normalize AI responses that contain raw LaTeX into readable Markdown/Unicode.
    Code blocks are preserved unchanged.
    """
    if not content:
        return content

    parts: list[tuple[str, str]] = []
    last_index = 0

    for match in _FENCED_CODE_PATTERN.finditer(content):
        if match.start() > last_index:
            parts.append(("text", content[last_index : match.start()]))
        parts.append(("code", match.group(1)))
        last_index = match.end()

    if last_index < len(content):
        parts.append(("text", content[last_index:]))

    if not parts:
        parts.append(("text", content))

    sanitized_segments: list[str] = []
    for kind, segment in parts:
        if kind == "code":
            sanitized_segments.append(segment)
            continue
        cleaned_segment = _INTERNAL_CONTEXT_TAG_PATTERN.sub("", segment)
        cleaned_segment = _INTERNAL_CONTEXT_LABEL_PATTERN.sub("", cleaned_segment)
        converted = _convert_math_delimiters(cleaned_segment)
        sanitized_segments.append(_replace_latex_symbols(converted))

    result = "".join(sanitized_segments)
    return re.sub(r"\n{3,}", "\n\n", result).strip()


class Message(BaseModel):
    role: ChatRole = Field(..., description="บทบาทของผู้ส่งข้อความ")
    content: str = Field(..., description="เนื้อหาของข้อความ")

    @classmethod
    def from_assistant(cls, content: str) -> "Message":
        return cls(
            role=ChatRole.ASSISTANT,
            content=sanitize_message_content(content or ""),
        )


class VisualizationContext(BaseModel):
    report_id: str = Field(..., min_length=1, max_length=64)
    widget_id: Optional[str] = Field(None, max_length=160)
    filters: Dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    messages: List[Message] = Field(..., description="ประวัติการสนทนาที่ผ่านมาทั้งหมด")
    locale: Literal["th", "en"] = Field(
        "th", description="Preferred UI and response locale"
    )
    model: Optional[str] = Field(None, description="โมเดลที่ต้องการเลือกใช้เฉพาะครั้งนี้ (ถ้ามี)")
    tier: UserTier = Field(UserTier.FREE, description="ระดับแผนการใช้งานของผู้ใช้")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0, description="ระดับความคิดสร้างสรรค์ (0.0 ถึง 2.0)")
    max_tokens: Optional[int] = Field(None, description="จำนวน Token สูงสุดที่ยอมให้ตอบกลับ")
    file_attachment_name: Optional[str] = Field(None, description="ชื่อไฟล์ที่แนบมาเพื่อวิเคราะห์")
    json_path: Optional[str] = Field(None, description="Nested JSON record-array path, e.g. items[]")
    column_mapping: Optional[Dict[str, str]] = Field(None, description="ข้อมูลการจับคู่คอลัมน์ที่ผู้ใช้กำหนด")
    cleaning_profile: Optional[str] = Field("standard", description="Data cleaning profile: standard, financial, conservative, or aggressive")
    cleaning_recipe: Optional[Dict[str, Any]] = Field(
        None, description="Explicit, user-approved deterministic ETL recipe"
    )
    data_setup_session_id: Optional[str] = Field(
        None, description="Owned ready Data Setup session authorizing this dataset version"
    )
    dataset_version_id: Optional[str] = Field(
        None, description="Owned immutable DatasetVersion used for analysis provenance"
    )
    user_id: str = Field(..., description="ID ของผู้ใช้งานที่ส่งคำขอ")
    connection_id: Optional[str] = Field(None, description="ID ของการเชื่อมต่อฐานข้อมูลหรือ API ที่อ้างอิง")
    connection_type: Optional[str] = Field(None, description="ประเภทของการเชื่อมต่อ ('sql' หรือ 'api')")
    sql_table: Optional[str] = Field(None, description="ชื่อตาราง SQL เมื่ออ้างอิง @connection-table")
    agent_session_id: Optional[str] = Field(None, description="Resume paused autonomous agent session")
    agent_clarification_answer: Optional[str] = Field(None, description="User answer to agent clarification question")
    conversation_id: Optional[str] = Field(
        None, description="Conversation UUID used for scoped memory and quality telemetry"
    )
    model_mode: Literal["auto", "fast", "deep"] = Field(
        "auto", description="Trusted model-routing preference, resolved against the user's tier"
    )
    orchestration_resolution: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Phase 6 structured resolution for awaiting_user "
            "(decision: approved|rejected|modified + optional context_updates)"
        ),
    )
    setup_intent: Optional[str] = Field(
        None,
        description=(
            "Phase 7.1/7.2.2 setup intents: prepare_attached_source_for_analysis, "
            "continue_workflow"
        ),
    )
    client_request_id: Optional[str] = Field(
        None,
        description="Client generation id used for usage settlement idempotency",
    )
    visualization_context: Optional[VisualizationContext] = Field(
        None,
        description="Owned Visualization report, focused widget and active filters",
    )

class ChatResponse(BaseModel):
    message: Message = Field(..., description="ข้อความคำตอบจาก AI")
    model_used: str = Field(..., description="ชื่อโมเดลจริงที่ระบบเลือกใช้ตอบกลับ")
    usage: Optional[TokenUsage] = Field(None, description="ข้อมูลจำนวน Token ที่ใช้ประมวลผล")
    agent_paused: bool = Field(False, description="Agent paused waiting for user clarification")
    agent_session_id: Optional[str] = Field(None, description="Session ID to resume after clarification")
    verification: Optional[Dict[str, Any]] = Field(
        None, description="Evidence and numeric-claim verification summary"
    )
    routing: Optional[Dict[str, Any]] = Field(
        None, description="Server-side intent and model-routing decision"
    )
    response_mode: Optional[Dict[str, Any]] = Field(
        None, description="Server-resolved execution mode and processing budgets"
    )
    analysis_audit: Optional[Dict[str, Any]] = Field(
        None, description="Structured finding provenance, formulas, eligibility and grain audit"
    )
    tool_execution: Optional[Dict[str, Any]] = Field(
        None,
        description="Server-owned analytical tool execution ledger and evidence policy",
    )
    orchestration: Optional[Dict[str, Any]] = Field(
        None,
        description="Phase 5 conversational setup orchestration payload (ask_user/tool/respond)",
    )
