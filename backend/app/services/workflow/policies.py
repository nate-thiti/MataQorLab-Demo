"""Reuse / skip / confirmation / fingerprint policies (Phase 4 / 4.5)."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping, Optional, Set

from app.services.workflow.models import (
    ConfirmationDecision,
    WorkflowStepStatus,
    WorkflowStepType,
)

# Conservative skip policy — no heuristic auto-skip.
SKIP_ALLOWED: Dict[str, bool] = {
    WorkflowStepType.INSPECT.value: False,
    WorkflowStepType.PREPARE.value: False,
    WorkflowStepType.CLEAN.value: True,   # only when caller explicitly requests
    WorkflowStepType.MAP.value: True,     # only with trusted existing mapping
    WorkflowStepType.VALIDATE.value: False,
    WorkflowStepType.FINALIZE.value: False,
}

# Structural policy flags (reason categories). Detection is separate.
CONFIRMATION_POLICIES: Dict[str, bool] = {
    "aggressive_cleaning": True,
    "ambiguous_mapping": True,
    "business_semantic_change": True,
    "destructive_cleaning": True,
    "business_contract_change": True,
}

CONFIRMATION_REASON_CODES = {
    "AGGRESSIVE_CLEANING",
    "AMBIGUOUS_MAPPING",
    "BUSINESS_CONTRACT_CHANGE",
    "DESTRUCTIVE_TRANSFORMATION",
    "SEMANTIC_MEANING_REQUIRED",
}

SATISFIED_DEP_STATUSES: Set[str] = {
    WorkflowStepStatus.COMPLETED.value,
    WorkflowStepStatus.SKIPPED.value,
}

FINGERPRINT_KEYS = frozenset({
    "source_fingerprint",
    "mapping_fp",
    "contract_fp",
    "cleaning_profile",
    "dataset_key",
    "recipe_hash",
    "confirmation_fingerprint",
})


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def mapping_fingerprint(mapping: Optional[Mapping[str, Any]]) -> str:
    normalized = {
        str(k): str(v).strip().lower()
        for k, v in (mapping or {}).items()
        if str(v or "").strip()
    }
    return _stable_hash(normalized)


def contract_fingerprint(contract: Optional[Mapping[str, Any]]) -> str:
    return _stable_hash(contract or {})


def has_input_fingerprint(stored_input: Optional[Mapping[str, Any]]) -> bool:
    """True when a step row carries reusable input identity metadata."""
    stored = stored_input or {}
    return any(key in stored for key in FINGERPRINT_KEYS if key != "confirmation_fingerprint")


def build_step_fingerprint(
    step_type: str,
    *,
    session: Mapping[str, Any],
    dataset_key: Optional[str] = None,
    cleaning_profile: Optional[str] = None,
) -> Dict[str, Any]:
    """Compact input fingerprint — never hashes full datasets."""
    source_fp = str(session.get("source_fingerprint") or "")
    mapping = session.get("column_mapping") or {}
    recipe = session.get("cleaning_recipe") or {}
    contract = (recipe.get("data_contract") if isinstance(recipe, dict) else None) or {}
    profile = cleaning_profile or session.get("cleaning_profile") or "standard"
    step = str(step_type)
    base = {
        "step_type": step,
        "source_fingerprint": source_fp,
        "source_type": session.get("source_type"),
    }
    if step == WorkflowStepType.INSPECT.value:
        return base
    if step == WorkflowStepType.PREPARE.value:
        return base
    if step == WorkflowStepType.MAP.value:
        return {**base, "mapping_fp": mapping_fingerprint(mapping)}
    if step == WorkflowStepType.VALIDATE.value:
        return {
            **base,
            "mapping_fp": mapping_fingerprint(mapping),
            "contract_fp": contract_fingerprint(contract),
        }
    if step == WorkflowStepType.CLEAN.value:
        # Mapping changes do not invalidate the cleaned artifact; finalize
        # re-applies mapping coercion. Track profile + source identity only.
        return {
            **base,
            "dataset_key": dataset_key or "",
            "cleaning_profile": profile,
        }
    if step == WorkflowStepType.FINALIZE.value:
        return {
            **base,
            "dataset_key": dataset_key or "",
            "cleaning_profile": profile,
            "mapping_fp": mapping_fingerprint(mapping),
            "contract_fp": contract_fingerprint(contract),
            "recipe_hash": session.get("recipe_hash") or "",
        }
    return base


def build_confirmation_fingerprint(
    step_type: str,
    *,
    session: Mapping[str, Any],
    proposed_input: Optional[Mapping[str, Any]] = None,
    reason_code: Optional[str] = None,
) -> str:
    """Bind a confirmation to the exact proposed action inputs (not datasets)."""
    payload = {
        "step_type": str(step_type),
        "reason_code": reason_code or "",
        "proposed": dict(proposed_input or build_step_fingerprint(step_type, session=session)),
    }
    return _stable_hash(payload)


def fingerprints_match(
    stored_input: Optional[Mapping[str, Any]],
    current: Mapping[str, Any],
) -> bool:
    if not stored_input:
        return False
    # Compare only fingerprint keys present in current.
    for key, value in current.items():
        if key == "step_type":
            continue
        if stored_input.get(key) != value:
            return False
    return True


def can_skip(step_type: str) -> bool:
    return bool(SKIP_ALLOWED.get(str(step_type), False))


def requires_confirmation(policy_key: str) -> bool:
    return bool(CONFIRMATION_POLICIES.get(str(policy_key), False))


def dependency_satisfied(step_row: Optional[Mapping[str, Any]]) -> bool:
    if not step_row:
        return False
    return str(step_row.get("status") or "") in SATISFIED_DEP_STATUSES


def cleaned_artifact_present(step_row: Optional[Mapping[str, Any]]) -> bool:
    if not step_row:
        return False
    output = step_row.get("output") or {}
    artifacts = output.get("artifacts") if isinstance(output, dict) else {}
    return bool((artifacts or {}).get("cleaned_artifact_key"))


def evaluate_confirmation_requirement(
    session: Mapping[str, Any],
    step_type: str,
    *,
    proposed_input: Optional[Mapping[str, Any]] = None,
    workflow_plan: Optional[Mapping[str, Any]] = None,
) -> ConfirmationDecision:
    """Deterministic confirmation gate for known high-confidence cases.

    Does not invent business semantics via LLM. Only auto-detects cases the
    backend can assert safely today.
    """
    del workflow_plan  # reserved for future richer plan-aware rules
    step = str(step_type)
    proposed = dict(
        proposed_input
        or build_step_fingerprint(step, session=session)
    )
    profile = str(
        proposed.get("cleaning_profile")
        or session.get("cleaning_profile")
        or "standard"
    ).strip().lower()

    # High-confidence: aggressive cleaning profile always requires confirmation.
    if step == WorkflowStepType.CLEAN.value and profile == "aggressive":
        if requires_confirmation("aggressive_cleaning"):
            reason_code = "AGGRESSIVE_CLEANING"
            fp = build_confirmation_fingerprint(
                step,
                session=session,
                proposed_input=proposed,
                reason_code=reason_code,
            )
            return ConfirmationDecision(
                required=True,
                reason_code=reason_code,
                reason="Aggressive cleaning profile requires explicit user confirmation.",
                context={"profile": profile},
                confirmation_fingerprint=fp,
            )

    # Supported mechanism: caller/session flag for ambiguous mapping.
    # Not auto-inferred from heuristics in Phase 4.5.
    mapping_flags = session.get("mapping_flags") or {}
    if step == WorkflowStepType.MAP.value and (
        session.get("require_mapping_confirmation")
        or mapping_flags.get("ambiguous")
    ):
        if requires_confirmation("ambiguous_mapping"):
            reason_code = "AMBIGUOUS_MAPPING"
            fp = build_confirmation_fingerprint(
                step,
                session=session,
                proposed_input=proposed,
                reason_code=reason_code,
            )
            return ConfirmationDecision(
                required=True,
                reason_code=reason_code,
                reason="Mapping marked ambiguous; confirmation required.",
                context={"mapping_flags": dict(mapping_flags) if isinstance(mapping_flags, dict) else {}},
                confirmation_fingerprint=fp,
            )

    # Supported mechanism: explicit contract-change flag on session/recipe.
    recipe = session.get("cleaning_recipe") or {}
    contract = (recipe.get("data_contract") if isinstance(recipe, dict) else None) or {}
    if step == WorkflowStepType.VALIDATE.value and (
        session.get("require_contract_confirmation")
        or (isinstance(contract, dict) and contract.get("requires_confirmation"))
    ):
        if requires_confirmation("business_contract_change"):
            reason_code = "BUSINESS_CONTRACT_CHANGE"
            fp = build_confirmation_fingerprint(
                step,
                session=session,
                proposed_input=proposed,
                reason_code=reason_code,
            )
            return ConfirmationDecision(
                required=True,
                reason_code=reason_code,
                reason="Business contract change requires confirmation.",
                context={"contract_fp": proposed.get("contract_fp")},
                confirmation_fingerprint=fp,
            )

    return ConfirmationDecision(required=False)


def approval_matches_proposed(
    step_row: Optional[Mapping[str, Any]],
    confirmation_fingerprint: str,
) -> bool:
    """True when a ready step carries a matching approved confirmation."""
    if not step_row:
        return False
    if str(step_row.get("status")) not in {
        WorkflowStepStatus.READY.value,
        WorkflowStepStatus.AWAITING_USER.value,
    }:
        # After approval, status is ready; also allow reading resolution from output.
        pass
    output = step_row.get("output") or {}
    metadata = output.get("metadata") if isinstance(output, dict) else {}
    resolution = (metadata or {}).get("resolution") or {}
    if str(resolution.get("decision") or "").lower() != "approved":
        return False
    stored_fp = (
        resolution.get("confirmation_fingerprint")
        or (step_row.get("input") or {}).get("confirmation_fingerprint")
    )
    return bool(stored_fp) and stored_fp == confirmation_fingerprint
