"""Structured AI orchestrator decisions (Phase 5) — not workflow authority."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


class AskUserOption(BaseModel):
    id: str
    label: str


class AskUserDecision(BaseModel):
    type: Literal["ask_user"] = "ask_user"
    question: str
    reason: Optional[str] = None
    context_key: Optional[str] = None
    decision_key: Optional[str] = None
    expected_answer_type: Optional[str] = None
    options: Optional[List[AskUserOption]] = None

    @field_validator("question")
    @classmethod
    def _question_nonempty(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("ask_user.question must be non-empty")
        return text


class ToolCallDecision(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    step_type: str
    reason: str = ""
    proposed_input: Dict[str, Any] = Field(default_factory=dict)
    capability_id: Optional[str] = None

    @field_validator("step_type")
    @classmethod
    def _step_nonempty(cls, value: str) -> str:
        text = str(value or "").strip().lower()
        if not text:
            raise ValueError("tool_call.step_type must be non-empty")
        return text


class RespondDecision(BaseModel):
    type: Literal["respond"] = "respond"
    message: str

    @field_validator("message")
    @classmethod
    def _message_nonempty(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("respond.message must be non-empty")
        return text


OrchestratorDecision = Union[AskUserDecision, ToolCallDecision, RespondDecision]


class UserResolutionProposal(BaseModel):
    """Parsed user answer for awaiting_user — engine still validates."""

    decision: Literal["approved", "rejected", "modified", "ambiguous"]
    context_updates: Dict[str, Any] = Field(default_factory=dict)
    note: Optional[str] = None


class OrchestratorResult(BaseModel):
    decision: OrchestratorDecision
    assistant_message: str
    workflow_plan: Optional[Dict[str, Any]] = None
    engine_result: Optional[Dict[str, Any]] = None
    awaiting_user: Optional[Dict[str, Any]] = None
    options: Optional[List[Dict[str, str]]] = None
    model_used: Optional[str] = None
    prompt_version: str = "1.0"
    audit: Dict[str, Any] = Field(default_factory=dict)
    llm_usage: Optional[Dict[str, Any]] = None
    worklog_stamps: List[Dict[str, Any]] = Field(default_factory=list)
    working_memory: Optional[Dict[str, Any]] = None
