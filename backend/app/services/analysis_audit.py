"""Build bounded, serializable audit packets for analytical responses."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List


def _verification_layers(
    findings: List[Dict[str, Any]],
    grain_intelligence: Dict[str, Any],
    data_contract: Dict[str, Any],
    decision_assurance: Dict[str, Any],
) -> Dict[str, Any]:
    computation_checks = {
        "findings_present": bool(findings),
        "result_hashes_present": bool(findings) and all(
            bool((item.get("provenance") or {}).get("result_hash"))
            for item in findings
        ),
    }
    computation_ok = all(computation_checks.values())

    readiness_checks = {
        "mapping_confirmed": bool(data_contract.get("mapping_confirmed")),
        "data_owner_recorded": bool(data_contract.get("data_owner")),
        "row_grain_recorded": bool(
            data_contract.get("row_grain") or grain_intelligence.get("grain")
        ),
        "metric_definition_recorded": bool(
            data_contract.get("metric_definition")
            or data_contract.get("metric_definitions")
        ),
        "period_complete": data_contract.get("period_status") == "complete",
    }
    readiness_ok = all(readiness_checks.values())

    business_checks = {
        "business_purpose_recorded": bool(data_contract.get("business_purpose")),
        "cancellation_policy_recorded": bool(
            data_contract.get("cancellation_policy")
        ),
        "business_context_reviewed": bool(
            data_contract.get("business_context_reviewed")
        ),
    }
    business_ok = all(business_checks.values())

    def layer(status: bool, checks: Dict[str, bool], scope: str) -> Dict[str, Any]:
        return {
            "status": "verified" if status else "needs_review",
            "scope": scope,
            "checks": checks,
            "missing": [key for key, passed in checks.items() if not passed],
        }

    confidence = decision_assurance.get("confidence_matrix") or {}
    causal = decision_assurance.get("causal_eligibility") or {}
    return {
        "computation": layer(
            computation_ok,
            computation_checks,
            "Formulas and result hashes for computed findings",
        ),
        "data_readiness": layer(
            readiness_ok,
            readiness_checks,
            "Mapping, ownership, grain, metric definition and period completeness",
        ),
        "business_context": layer(
            business_ok,
            business_checks,
            "Human-reviewed business meaning and operating context",
        ),
        "evidence_assurance": layer(
            float(confidence.get("overall_score") or 0) >= 0.6,
            {
                "claim_graph_present": bool(
                    (decision_assurance.get("claim_graph") or {}).get("claim_count")
                ),
                "support_score_moderate": float(
                    confidence.get("overall_score") or 0
                ) >= 0.6,
                "evidence_gaps_resolved": not bool(
                    decision_assurance.get("evidence_requests")
                ),
            },
            "Claim support, evidence provenance and unresolved evidence gaps",
        ),
        "causal_assurance": layer(
            causal.get("status") == "eligible",
            {
                "causal_design_eligible": causal.get("status") == "eligible",
                "eligible_method_available": any(
                    item.get("status") == "eligible"
                    for item in (causal.get("methods") or {}).values()
                ),
            },
            "Method-specific causal design eligibility; descriptive analysis remains available",
        ),
    }


def build_analysis_audit(
    *,
    findings: List[Dict[str, Any]],
    question_plan: Dict[str, Any],
    eligibility: Dict[str, Any],
    column_intelligence: Dict[str, Any],
    grain_intelligence: Dict[str, Any],
    compute_depth: str,
    data_contract: Dict[str, Any] | None = None,
    decision_assurance: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    contract = dict(data_contract or {})
    assurance = dict(decision_assurance or {})
    verification_layers = _verification_layers(
        findings,
        grain_intelligence,
        contract,
        assurance,
    )
    identity = {
        "finding_ids": [item.get("id") for item in findings],
        "question_plan": question_plan,
        "compute_depth": compute_depth,
        "data_contract": contract,
        "decision_assurance_id": assurance.get("packet_id"),
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()[:20]
    return {
        "audit_id": f"audit_{digest}",
        "contract_version": "2.0",
        "compute_depth": compute_depth,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": len(findings),
        "findings": findings,
        "question_plan": question_plan,
        "eligibility": eligibility,
        "column_intelligence": column_intelligence,
        "grain_intelligence": grain_intelligence,
        "data_contract": contract,
        "decision_assurance": assurance,
        "verification_layers": verification_layers,
        "assurance_note": (
            "Computed verification confirms consistency with the supplied data and "
            "formulas; it does not independently establish business truth."
        ),
    }
