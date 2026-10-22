"""Deterministic analysis plan used to constrain compute and narration."""
from __future__ import annotations

import re
from typing import Any, Dict, List


def decompose_analysis_question(
    question: str,
    *,
    roles: Dict[str, str],
    compute_depth: str,
) -> Dict[str, Any]:
    text = (question or "").lower()
    steps: List[Dict[str, Any]] = []

    def add(step_id: str, operation: str, requires: List[str]) -> None:
        if step_id not in {item["id"] for item in steps}:
            steps.append(
                {
                    "id": step_id,
                    "operation": operation,
                    "requires": requires,
                    "status": "eligible"
                    if all(any(role == req or role.startswith(req) for role in roles) for req in requires)
                    else "needs_columns",
                }
            )

    add("baseline", "profile dataset size, quality, and core measures", [])
    if re.search(r"\b(why|cause|driver|contribution)\b|ทำไม|สาเหตุ|ปัจจัย", text):
        add("drivers", "attribute period change by business dimension", ["date"])
    if re.search(r"\b(trend|growth|mom|yoy|wow|forecast)\b|แนวโน้ม|เติบโต|เทียบ", text):
        add("time_comparison", "compute comparable-period growth", ["date"])
    if re.search(r"\b(top|best|largest|pareto|concentration)\b|สูงสุด|อันดับ|กระจุก", text):
        add("concentration", "rank dimensions and calculate Pareto concentration", [])
    if re.search(r"\b(retention|cohort|repeat)\b|กลับมา|รักษาลูกค้า", text):
        add("cohort", "calculate cohort retention when entity/activity grain is valid", ["date"])
    if compute_depth == "deep":
        add("robustness", "run eligibility-gated change-point, seasonality, and anomaly screens", [])
    steps.append(
        {
            "id": "verification",
            "operation": "compare every numeric claim with structured findings",
            "requires": [],
            "status": "eligible",
        }
    )
    return {
        "compute_depth": compute_depth,
        "steps": steps,
        "narration_contract": [
            "evidence",
            "interpretation",
            "suggested_action",
        ],
    }
