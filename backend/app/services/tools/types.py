"""Shared contracts for Phase 2 setup tool wrappers."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ToolStatus = Literal[
    "completed",
    "failed",
    "skipped",
    "awaiting_user",
]


class ToolResult(BaseModel):
    """Compact structured result — never carries full datasets."""

    tool: str
    status: ToolStatus = "completed"
    summary: Optional[str] = None
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    suggested_next_actions: List[str] = Field(default_factory=list)

    def to_public_dict(self) -> Dict[str, Any]:
        return self.model_dump()
