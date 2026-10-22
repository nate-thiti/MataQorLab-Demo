"""Deterministic session context updates from orchestrator resolutions."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from app.core.json_safety import to_json_safe
from app.services.etl_pipeline import normalize_data_contract

logger = logging.getLogger("mataqorlab.orchestrator.session_updates")

_ALLOWED_PROFILES = {"standard", "financial", "conservative", "aggressive"}
_CONTRACT_TEXT_KEYS = {
    "row_grain",
    "business_purpose",
    "data_owner",
    "metric_definition",
    "period_status",
}
_CONTRACT_BOOL_KEYS = {
    "mapping_confirmed",
    "business_context_reviewed",
}


def _patch_contract(
    current: Dict[str, Any],
    mutator,
) -> Dict[str, Any]:
    recipe = dict(current.get("cleaning_recipe") or {})
    contract = dict(recipe.get("data_contract") or {})
    preserved_return = contract.get("return_policy")
    mutator(contract)
    try:
        normalized = normalize_data_contract(contract)
        # normalize drops unknown structured fields — reattach confirmed return_policy.
        if preserved_return is not None:
            normalized["return_policy"] = preserved_return
        if contract.get("return_policy") is not None:
            normalized["return_policy"] = contract.get("return_policy")
        contract = normalized
    except Exception as exc:
        logger.warning(
            "normalize_data_contract_failed",
            extra={"error": str(exc)[:200]},
        )
        raise ValueError(f"invalid_data_contract:{exc}") from exc
    recipe["data_contract"] = contract
    return recipe


def apply_context_updates(
    client: Any,
    *,
    session_id: str,
    user_id: str,
    session: Mapping[str, Any],
    context_updates: Mapping[str, Any],
) -> Dict[str, Any]:
    """Apply a narrow allowlist of session updates. Returns updated session dict."""
    updates: Dict[str, Any] = {}
    current = dict(session)

    profile = context_updates.get("cleaning_profile")
    if profile is not None:
        profile_s = str(profile).strip().lower()
        if profile_s not in _ALLOWED_PROFILES:
            raise ValueError(f"Unsupported cleaning_profile: {profile_s}")
        updates["cleaning_profile"] = profile_s
        current["cleaning_profile"] = profile_s

    contract_touched = False

    def _mutate(contract: Dict[str, Any]) -> None:
        nonlocal contract_touched
        if "return_policy" in context_updates:
            policy = context_updates.get("return_policy")
            if isinstance(policy, Mapping):
                contract["return_policy"] = {
                    "value": str(policy.get("value") or "")[:100],
                    "treatment": str(policy.get("treatment") or "")[:100],
                    "source": "user_confirmed",
                }
                contract_touched = True
        for key in _CONTRACT_TEXT_KEYS:
            if key not in context_updates:
                continue
            contract[key] = str(context_updates.get(key) or "").strip()[:1000]
            contract_touched = True
        for key in _CONTRACT_BOOL_KEYS:
            if key not in context_updates:
                continue
            contract[key] = bool(context_updates.get(key))
            contract_touched = True
        # Auto-mark context reviewed once core business fields exist.
        if (
            contract.get("row_grain")
            and contract.get("business_purpose")
            and contract.get("metric_definition")
            and context_updates.get("business_context_reviewed") is not False
        ):
            # Do not force true unless explicitly set or nearly complete.
            pass

    if any(
        k in context_updates
        for k in ("return_policy", *_CONTRACT_TEXT_KEYS, *_CONTRACT_BOOL_KEYS)
    ):
        recipe = _patch_contract(current, _mutate)
        if contract_touched:
            updates["cleaning_recipe"] = to_json_safe(recipe)
            current["cleaning_recipe"] = recipe

    mapping_patch = context_updates.get("column_mapping")
    if isinstance(mapping_patch, Mapping) and mapping_patch:
        mapping = dict(current.get("column_mapping") or {})
        for column, role in mapping_patch.items():
            col = str(column).strip()
            role_s = str(role).strip().lower()
            if not col or not role_s or len(col) > 200:
                continue
            mapping[col] = role_s
        updates["column_mapping"] = mapping
        current["column_mapping"] = mapping

    if not updates:
        return current

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    client.table("data_setup_sessions").update(updates).eq(
        "id", session_id
    ).eq("user_id", user_id).execute()
    logger.info(
        "orchestrator_session_updated",
        extra={
            "session_id": session_id,
            "keys": sorted(updates.keys()),
        },
    )
    current.update(updates)
    return current
