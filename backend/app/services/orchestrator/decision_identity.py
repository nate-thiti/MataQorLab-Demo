"""Decision resolution identity — confirmed decisions must not regenerate."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping, Optional

from app.services.etl_pipeline import normalize_data_contract
from app.services.workflow.policies import contract_fingerprint, mapping_fingerprint

# Map unresolved decision_key → contract / session fields used for confirmation.
_DECISION_VALUE_KEYS: Dict[str, str] = {
    "row_grain": "row_grain",
    "primary_metric": "metric_definition",
    "metric_definition": "metric_definition",
    "business_purpose": "business_purpose",
    "data_owner": "data_owner",
    "reporting_period_status": "period_status",
    "period_status": "period_status",
    "return_policy": "return_policy",
    "cancellation_policy": "cancellation_policy",
    "mapping_confirmed": "mapping_confirmed",
    "business_context_reviewed": "business_context_reviewed",
}


def is_original_prompt_capture(
    session: Mapping[str, Any],
    decision_key: str,
    value: Any,
) -> bool:
    """Detect the historical bug where kickoff prose was persisted as contract input."""
    original = str(session.get("original_prompt") or "").strip()
    candidate = str(value or "").strip()
    if not original or not candidate or candidate != original:
        return False
    return decision_key in {
        "row_grain",
        "primary_metric",
        "metric_definition",
        "business_purpose",
        "data_owner",
    } or str(decision_key).startswith("mapping:")


def decision_context_fingerprint(
    session: Mapping[str, Any],
    decision_key: str,
) -> str:
    """Fingerprint of inputs that define whether a decision answer is still valid."""
    recipe = session.get("cleaning_recipe") or {}
    contract_raw = recipe.get("data_contract") if isinstance(recipe, Mapping) else {}
    contract = normalize_data_contract(contract_raw)
    if isinstance(contract_raw, Mapping) and contract_raw.get("return_policy"):
        contract = dict(contract)
        contract["return_policy"] = contract_raw.get("return_policy")
    mapping = dict(session.get("column_mapping") or {})
    payload = {
        "session_id": str(session.get("id") or ""),
        "source_fingerprint": str(session.get("source_fingerprint") or ""),
        "decision_key": str(decision_key),
        "mapping_fp": mapping_fingerprint(mapping),
        "contract_fp": contract_fingerprint(contract),
    }
    if str(decision_key).startswith("mapping:"):
        payload["role"] = str(decision_key).split(":", 1)[1]
        payload["mapped_roles"] = sorted({str(v) for v in mapping.values() if v})
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _contract_value(session: Mapping[str, Any], decision_key: str) -> Any:
    recipe = session.get("cleaning_recipe") or {}
    contract_raw = recipe.get("data_contract") if isinstance(recipe, Mapping) else {}
    contract = normalize_data_contract(contract_raw)
    if decision_key == "return_policy":
        policy = (contract_raw or {}).get("return_policy") if isinstance(contract_raw, Mapping) else None
        if isinstance(policy, Mapping):
            return policy.get("value") or policy.get("treatment")
        return policy
    if decision_key.startswith("mapping:"):
        role = decision_key.split(":", 1)[1]
        mapping = dict(session.get("column_mapping") or {})
        for _col, mapped_role in mapping.items():
            if str(mapped_role).strip().lower() == role.lower():
                return str(_col)
        return None
    field = _DECISION_VALUE_KEYS.get(decision_key, decision_key)
    if field in {"mapping_confirmed", "business_context_reviewed"}:
        return bool(contract.get(field))
    return contract.get(field)


def _confirmed_from_progress(
    session: Mapping[str, Any],
    decision_key: str,
) -> Optional[Dict[str, Any]]:
    progress = session.get("processing_progress") or {}
    if not isinstance(progress, Mapping):
        return None
    confirmed = progress.get("confirmed_decisions") or {}
    if not isinstance(confirmed, Mapping):
        return None
    entry = confirmed.get(decision_key)
    return dict(entry) if isinstance(entry, Mapping) else None


def is_decision_confirmed(
    session: Mapping[str, Any],
    decision_key: str,
) -> bool:
    """True when backend truth shows a user-confirmed value for this decision."""
    entry = _confirmed_from_progress(session, decision_key)
    current_fp = decision_context_fingerprint(session, decision_key)
    bool_gates = {"mapping_confirmed", "business_context_reviewed"}
    if entry:
        if str(entry.get("source") or "") != "user_confirmed":
            return False
        stored = entry.get("value")
        # Bool readiness gates are confirmed only when explicitly True.
        if decision_key in bool_gates:
            if stored is True or str(stored).strip().lower() in {"true", "1", "yes", "approved", "approve"}:
                pass
            else:
                return False
        elif not stored and stored != False:
            return False
        if is_original_prompt_capture(session, decision_key, stored):
            return False
        stored_fp = str(entry.get("fingerprint") or "")
        if stored_fp and stored_fp != current_fp:
            return False
        return True

    value = _contract_value(session, decision_key)
    if is_original_prompt_capture(session, decision_key, value):
        return False
    if decision_key.startswith("mapping:"):
        return bool(str(value or "").strip())
    if decision_key in bool_gates:
        return bool(value) is True
    if decision_key == "return_policy":
        policy = value
        return bool(policy)
    if decision_key in {"reporting_period_status", "period_status"}:
        return str(value or "unknown") != "unknown"
    return bool(str(value or "").strip())


def record_confirmed_decision(
    progress: Dict[str, Any],
    *,
    session: Mapping[str, Any],
    decision_key: str,
    value: Any,
) -> Dict[str, Any]:
    confirmed = dict(progress.get("confirmed_decisions") or {})
    fp = decision_context_fingerprint(session, decision_key)
    prev = confirmed.get(decision_key) if isinstance(confirmed.get(decision_key), Mapping) else {}
    version = int(prev.get("version") or 0) + 1
    confirmed[str(decision_key)] = {
        "value": value,
        "source": "user_confirmed",
        "fingerprint": fp,
        "version": version,
    }
    progress["confirmed_decisions"] = confirmed
    progress["resolved_decision_key"] = str(decision_key)
    progress.pop("active_decision", None)
    return progress
