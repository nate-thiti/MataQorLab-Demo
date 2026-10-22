"""validate_data — data contract and setup readiness checks."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from app.services.etl_pipeline import normalize_data_contract, validate_data_contract
from app.services.semantic_mapping_gate import evaluate_semantic_mapping_gate
from app.services.tools.types import ToolResult


def validate_data(
    *,
    data_contract: Optional[Mapping[str, Any]] = None,
    column_mapping: Optional[Mapping[str, Any]] = None,
    columns: Optional[List[str]] = None,
    suggested_mapping: Optional[Mapping[str, Any]] = None,
) -> ToolResult:
    """Evaluate contract/mapping readiness without claiming business truth.

    Keeps MataQorLab assurance concepts separate:
    - Computation readiness is owned by decision_assurance (analysis time)
    - Data readiness / business-context flags live on the contract and are
      reported here as structured metadata only
    """
    mapping = {
        str(column): str(role).strip().lower()
        for column, role in (column_mapping or {}).items()
        if str(role or "").strip()
    }
    contract = normalize_data_contract(data_contract)
    readiness = validate_data_contract(contract, mapping, columns)
    mapping_gate = evaluate_semantic_mapping_gate(
        mapping=mapping,
        data_contract=contract,
        columns=columns,
        suggested_mapping=suggested_mapping,
        require_confirmation=True,
    )

    findings: List[Dict[str, Any]] = []
    for error in readiness.get("errors") or []:
        findings.append({"severity": "error", **dict(error)})
    for warning in readiness.get("warnings") or []:
        findings.append({"severity": "warning", **dict(warning)})
    for issue in mapping_gate["issues"]:
        findings.append({"severity": "error", **dict(issue)})

    status = "completed"
    if readiness.get("status") == "invalid":
        status = "failed"
    elif readiness.get("status") == "needs_review" or not mapping_gate["ready"]:
        status = "awaiting_user"

    # Surface setup flags without collapsing assurance dimensions.
    business_context = {
        "business_context_reviewed": bool(contract.get("business_context_reviewed")),
        "mapping_confirmed": bool(contract.get("mapping_confirmed")),
        "data_owner": contract.get("data_owner") or "",
        "row_grain": contract.get("row_grain") or "",
    }
    data_readiness = {
        "contract_status": readiness.get("status"),
        "score": readiness.get("score"),
        "missing": readiness.get("missing") or [],
    }

    return ToolResult(
        tool="validate_data",
        status=status,  # type: ignore[arg-type]
        summary=(
            f"Data contract status: {readiness.get('status')} "
            f"(score={readiness.get('score')})"
        ),
        findings=findings,
        warnings=[item for item in findings if item.get("severity") == "warning"],
        artifacts={
            "data_contract": contract,
            "contract_readiness": readiness,
            "semantic_mapping_gate": mapping_gate,
        },
        metadata={
            "data_readiness": data_readiness,
            "business_context": business_context,
            # Computation is intentionally not evaluated here.
            "computation": {"evaluated": False, "owner": "decision_assurance"},
            "mapped_columns": len(mapping),
            "semantic_mapping_ready": mapping_gate["ready"],
        },
        suggested_next_actions=(
            ["finalize"]
            if readiness.get("status") == "ready" and mapping_gate["ready"]
            else ["ask_user", "map_schema"]
        ),
    )
