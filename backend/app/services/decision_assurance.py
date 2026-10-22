"""Decision assurance primitives for claims, evidence and causal analysis.

All scores and analyses are deterministic.  The module deliberately fails closed:
causal methods only run after their method-specific eligibility checks pass.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.services.dataset_engine import DatasetHandle


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _bounded_text(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _date(value: Any) -> Optional[pd.Timestamp]:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return parsed.tz_convert(None)


def _roles(analytics_results: Optional[Dict[str, Any]]) -> Dict[str, str]:
    return {
        str(role): str(column)
        for role, column in ((analytics_results or {}).get("detected_roles") or {}).items()
        if column
    }


def _first_existing(columns: Iterable[str], candidates: Iterable[Any]) -> Optional[str]:
    available = {str(column) for column in columns}
    for candidate in candidates:
        if candidate and str(candidate) in available:
            return str(candidate)
    return None


def _infer_column(columns: Iterable[str], pattern: str) -> Optional[str]:
    return next((str(column) for column in columns if re.search(pattern, str(column), re.I)), None)


def build_claim_evidence_graph(
    findings: List[Dict[str, Any]],
    *,
    web_sources: Optional[List[Dict[str, Any]]] = None,
    data_contract: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create an auditable graph without treating context as proof."""
    contract = data_contract or {}
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for finding in findings[:50]:
        claim_id = f"claim_{finding.get('id') or _hash(finding)}"
        provenance = finding.get("provenance") or {}
        evidence_id = f"evidence_result_{provenance.get('result_hash') or _hash(finding)}"
        nodes.extend([
            {
                "id": claim_id,
                "kind": "claim",
                "label": _bounded_text(finding.get("metric"), 200),
                "statement": _bounded_text(
                    finding.get("interpretation") or finding.get("evidence"), 500
                ),
                "finding_id": finding.get("id"),
                "claim_scope": "descriptive",
            },
            {
                "id": evidence_id,
                "kind": "computed_evidence",
                "label": _bounded_text(finding.get("evidence"), 300),
                "result_hash": provenance.get("result_hash"),
                "query_hash": provenance.get("query_hash"),
                "engine": provenance.get("engine"),
                "row_count": provenance.get("row_count"),
                "source_columns": list(provenance.get("source_columns") or [])[:50],
            },
        ])
        edges.append({
            "from": evidence_id,
            "to": claim_id,
            "relation": "supports",
            "strength": "direct_computation",
        })

    if contract:
        contract_id = f"evidence_contract_{_hash(contract)}"
        nodes.append({
            "id": contract_id,
            "kind": "business_context",
            "label": "User-approved data contract",
            "reviewed": bool(contract.get("business_context_reviewed")),
            "version": contract.get("contract_version"),
        })
        for node in [item for item in nodes if item.get("kind") == "claim"]:
            edges.append({
                "from": contract_id,
                "to": node["id"],
                "relation": "contextualizes",
                "strength": "human_reviewed" if contract.get("business_context_reviewed") else "unreviewed",
            })

    for index, source in enumerate((web_sources or [])[:20]):
        source_id = f"evidence_external_{_hash(source.get('url') or source)}"
        nodes.append({
            "id": source_id,
            "kind": "external_evidence",
            "label": _bounded_text(source.get("title") or source.get("url"), 300),
            "url": _bounded_text(source.get("url"), 1000),
            "snippet": _bounded_text(source.get("snippet"), 500),
            "published_at": source.get("published_at") or source.get("date"),
            "query": _bounded_text(source.get("query"), 300),
            "ordinal": index,
        })
        # Search results are context until a human or verifier explicitly links them.
        for node in [item for item in nodes if item.get("kind") == "claim"][:10]:
            edges.append({
                "from": source_id,
                "to": node["id"],
                "relation": "contextualizes",
                "strength": "unverified_external_context",
            })

    return {
        "version": "claim_evidence_graph_v1",
        "nodes": nodes[:150],
        "edges": edges[:300],
        "claim_count": sum(item["kind"] == "claim" for item in nodes),
        "evidence_count": sum(item["kind"] != "claim" for item in nodes),
        "relation_policy": (
            "Computed results may support descriptive claims. External sources only "
            "contextualize claims until their relevance and dates are verified."
        ),
    }


def build_truth_confidence_matrix(
    findings: List[Dict[str, Any]],
    *,
    data_contract: Optional[Dict[str, Any]] = None,
    web_sources: Optional[List[Dict[str, Any]]] = None,
    causal_eligibility: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Score evidence assurance, never the probability that a claim is true."""
    contract = data_contract or {}
    provenance_complete = bool(findings) and all(
        (item.get("provenance") or {}).get("result_hash") for item in findings
    )
    formulas_present = bool(findings) and all(
        (item.get("audit") or {}).get("formula")
        or (item.get("audit") or {}).get("sql")
        or (item.get("provenance") or {}).get("engine")
        for item in findings
    )
    causal_methods = (causal_eligibility or {}).get("methods") or {}
    causal_score = 1.0 if any(
        item.get("status") == "eligible" for item in causal_methods.values()
    ) else 0.25
    dimensions = {
        "computation": {
            "score": round((float(provenance_complete) + float(formulas_present)) / 2, 3),
            "basis": ["result hashes", "formula/SQL or deterministic engine"],
        },
        "data_readiness": {
            "score": round(sum([
                bool(contract.get("mapping_confirmed")),
                bool(contract.get("data_owner")),
                bool(contract.get("row_grain")),
                contract.get("period_status") == "complete",
            ]) / 4, 3),
            "basis": ["mapping", "owner", "grain", "period completeness"],
        },
        "business_context": {
            "score": round(sum([
                bool(contract.get("business_purpose")),
                bool(contract.get("business_context_reviewed")),
                bool(contract.get("metric_definition") or contract.get("metric_definitions")),
            ]) / 3, 3),
            "basis": ["purpose", "owner review", "metric definition"],
        },
        "freshness": {
            "score": 1.0 if contract.get("as_of_date") and contract.get("freshness_sla") else (
                0.6 if contract.get("as_of_date") else 0.25
            ),
            "basis": ["as-of date", "freshness SLA"],
        },
        "external_evidence": {
            "score": min(1.0, len(web_sources or []) / 3),
            "basis": ["dated and relevant external sources require human verification"],
        },
        "causal_support": {
            "score": causal_score,
            "basis": ["method-specific causal eligibility gate"],
        },
    }
    weights = {
        "computation": 0.3,
        "data_readiness": 0.2,
        "business_context": 0.2,
        "freshness": 0.1,
        "external_evidence": 0.05,
        "causal_support": 0.15,
    }
    overall = round(sum(dimensions[key]["score"] * weight for key, weight in weights.items()), 3)
    label = "high" if overall >= 0.8 else "moderate" if overall >= 0.6 else "low" if overall >= 0.35 else "insufficient"
    return {
        "version": "evidence_assurance_matrix_v1",
        "overall_score": overall,
        "label": label,
        "dimensions": dimensions,
        "score_meaning": "Confidence in the available support and controls, not truth probability.",
    }


def build_external_event_timeline(
    findings: List[Dict[str, Any]],
    *,
    web_sources: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    for finding in findings[:50]:
        period = (finding.get("provenance") or {}).get("period")
        event_date = _date(period)
        if event_date is not None or finding.get("type") in {"change_point", "anomaly"}:
            events.append({
                "id": f"event_internal_{finding.get('id') or _hash(finding)}",
                "kind": "internal",
                "date": event_date.date().isoformat() if event_date is not None else None,
                "label": _bounded_text(finding.get("metric"), 200),
                "finding_id": finding.get("id"),
                "date_status": "verified_from_finding" if event_date is not None else "missing",
            })
    for source in (web_sources or [])[:20]:
        raw_date = source.get("published_at") or source.get("date")
        event_date = _date(raw_date)
        events.append({
            "id": f"event_external_{_hash(source.get('url') or source)}",
            "kind": "external",
            "date": event_date.date().isoformat() if event_date is not None else None,
            "label": _bounded_text(source.get("title") or source.get("url"), 300),
            "url": _bounded_text(source.get("url"), 1000),
            "date_status": "source_provided" if event_date is not None else "undated",
        })
    dated_internal = [event for event in events if event["kind"] == "internal" and event["date"]]
    alignments: List[Dict[str, Any]] = []
    for external in [event for event in events if event["kind"] == "external" and event["date"]]:
        external_date = _date(external["date"])
        if external_date is None or not dated_internal:
            continue
        nearest = min(dated_internal, key=lambda item: abs((_date(item["date"]) - external_date).days))
        lag = int((_date(nearest["date"]) - external_date).days)
        alignments.append({
            "external_event_id": external["id"],
            "internal_event_id": nearest["id"],
            "lag_days": lag,
            "relation": "coincident" if abs(lag) <= 3 else "precedes" if lag > 0 else "follows",
            "causal_interpretation": False,
        })
    return {
        "version": "event_timeline_v1",
        "events": sorted(events, key=lambda item: (item["date"] is None, item["date"] or "", item["kind"])),
        "alignments": alignments,
        "warning": "Temporal alignment is not evidence of causation.",
    }


def _causal_design(
    columns: List[str],
    contract: Dict[str, Any],
    analytics_results: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    design = dict(contract.get("causal_design") or {})
    roles = _roles(analytics_results)
    date_col = _first_existing(columns, [design.get("date_column"), roles.get("date"), roles.get("timestamp")])
    date_col = date_col or _infer_column(columns, r"(date|time|month|period)")
    outcome = _first_existing(columns, [design.get("outcome_column"), roles.get("revenue"), roles.get("sales"), roles.get("profit")])
    if not outcome:
        outcome = _infer_column(columns, r"(outcome|revenue|sales|profit|amount|value)")
    treatment = _first_existing(columns, [design.get("treatment_column")])
    treatment = treatment or _infer_column(columns, r"(treated|treatment|intervention)")
    group = _first_existing(columns, [design.get("group_column"), roles.get("region"), roles.get("branch")])
    predictors = [
        item for item in (design.get("predictor_columns") or []) if item in columns
    ]
    return {
        **design,
        "date_column": date_col,
        "outcome_column": outcome,
        "treatment_column": treatment,
        "group_column": group,
        "predictor_columns": predictors,
    }


def build_causal_eligibility(
    handle: DatasetHandle,
    *,
    data_contract: Optional[Dict[str, Any]] = None,
    analytics_results: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sample = handle.to_pandas(limit=min(handle.row_count(), 100_000))
    design = _causal_design(list(sample.columns), data_contract or {}, analytics_results)
    date_col, outcome = design.get("date_column"), design.get("outcome_column")
    intervention = _date(design.get("intervention_date"))
    periods_pre = periods_post = 0
    valid_outcome = False
    if outcome in sample:
        valid_outcome = pd.to_numeric(sample[outcome], errors="coerce").notna().sum() >= 8
    if date_col in sample and intervention is not None:
        dates = pd.to_datetime(sample[date_col], errors="coerce", utc=True).dt.tz_localize(None)
        unique = pd.Series(dates.dropna().unique())
        periods_pre = int((unique < intervention).sum())
        periods_post = int((unique >= intervention).sum())

    def method(requirements: Dict[str, bool], minimums: Dict[str, Any]) -> Dict[str, Any]:
        missing = [key for key, passed in requirements.items() if not passed]
        return {
            "status": "eligible" if not missing else "needs_input",
            "checks": requirements,
            "missing": missing,
            "minimums": minimums,
        }

    treatment_col = design.get("treatment_column")
    treatment_values = (
        int(sample[treatment_col].dropna().nunique()) if treatment_col in sample else 0
    )
    group_col = design.get("group_column")
    group_values = int(sample[group_col].dropna().nunique()) if group_col in sample else 0
    methods = {
        "interrupted_time_series": method({
            "date_column": bool(date_col),
            "numeric_outcome": valid_outcome,
            "intervention_date": intervention is not None,
            "minimum_pre_periods": periods_pre >= 12,
            "minimum_post_periods": periods_post >= 8,
        }, {"pre_periods": 12, "post_periods": 8}),
        "difference_in_differences": method({
            "date_column": bool(date_col),
            "numeric_outcome": valid_outcome,
            "intervention_date": intervention is not None,
            "treatment_indicator_with_two_groups": bool(treatment_col and treatment_values == 2),
            "group_column": bool(group_col and group_values >= 2),
            "minimum_pre_periods": periods_pre >= 4,
            "minimum_post_periods": periods_post >= 4,
        }, {"pre_periods": 4, "post_periods": 4, "treatment_groups": 2}),
        "counterfactual": method({
            "date_column": bool(date_col),
            "numeric_outcome": valid_outcome,
            "intervention_date": intervention is not None,
            "predictors": bool(design.get("predictor_columns")),
            "minimum_pre_periods": periods_pre >= 20,
            "minimum_post_periods": periods_post >= 6,
        }, {"pre_periods": 20, "post_periods": 6, "predictors": 1}),
    }
    return {
        "version": "causal_eligibility_v1",
        "status": "eligible" if any(item["status"] == "eligible" for item in methods.values()) else "needs_input",
        "design": design,
        "observed": {
            "rows": len(sample),
            "pre_periods": periods_pre,
            "post_periods": periods_post,
            "treatment_values": treatment_values,
            "group_values": group_values,
        },
        "methods": methods,
        "policy": "Causal estimators are blocked until every method-specific check passes.",
    }


def _ols(x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    beta, _, _, _ = np.linalg.lstsq(x, y, rcond=None)
    residuals = y - x @ beta
    dof = max(1, len(y) - x.shape[1])
    sigma2 = float(residuals @ residuals) / dof
    covariance = sigma2 * np.linalg.pinv(x.T @ x)
    return beta, np.sqrt(np.maximum(0, np.diag(covariance)))


def run_causal_analyses(
    handle: DatasetHandle,
    eligibility: Dict[str, Any],
) -> Dict[str, Any]:
    df = handle.to_pandas(limit=min(handle.row_count(), 200_000)).copy()
    design = eligibility.get("design") or {}
    date_col, outcome = design.get("date_column"), design.get("outcome_column")
    intervention = _date(design.get("intervention_date"))
    results: Dict[str, Any] = {}
    if not date_col or not outcome or intervention is None:
        return {"version": "causal_results_v1", "results": {}, "blocked": True}
    df["_date"] = pd.to_datetime(df[date_col], errors="coerce", utc=True).dt.tz_localize(None)
    df["_outcome"] = pd.to_numeric(df[outcome], errors="coerce")
    df = df.dropna(subset=["_date", "_outcome"])

    if eligibility["methods"]["interrupted_time_series"]["status"] == "eligible":
        series = df.groupby("_date", as_index=False)["_outcome"].mean().sort_values("_date")
        t = np.arange(len(series), dtype=float)
        post = (series["_date"] >= intervention).astype(float).to_numpy()
        first_post = int(np.argmax(post)) if post.any() else len(series)
        after = np.maximum(0, t - first_post + 1) * post
        x = np.column_stack([np.ones(len(series)), t, post, after])
        beta, se = _ols(x, series["_outcome"].to_numpy(dtype=float))
        results["interrupted_time_series"] = {
            "status": "completed",
            "level_change": float(beta[2]),
            "level_change_95ci": [float(beta[2] - 1.96 * se[2]), float(beta[2] + 1.96 * se[2])],
            "slope_change": float(beta[3]),
            "periods": len(series),
            "interpretation": "Segmented-regression estimate conditional on the recorded intervention date.",
        }

    if eligibility["methods"]["difference_in_differences"]["status"] == "eligible":
        treatment_col = design["treatment_column"]
        treated_value = design.get("treatment_value")
        values = list(df[treatment_col].dropna().unique())
        if treated_value not in values:
            treated_value = values[-1]
        df["_treated"] = (df[treatment_col].astype(str) == str(treated_value)).astype(int)
        df["_post"] = (df["_date"] >= intervention).astype(int)
        cells = df.groupby(["_treated", "_post"])["_outcome"].agg(["mean", "count"])
        if all(key in cells.index for key in [(0, 0), (0, 1), (1, 0), (1, 1)]):
            estimate = (
                cells.loc[(1, 1), "mean"] - cells.loc[(1, 0), "mean"]
                - cells.loc[(0, 1), "mean"] + cells.loc[(0, 0), "mean"]
            )
            results["difference_in_differences"] = {
                "status": "completed",
                "estimate": float(estimate),
                "cell_counts": {
                    f"{treated}_{post}": int(cells.loc[(treated, post), "count"])
                    for treated, post in [(0, 0), (0, 1), (1, 0), (1, 1)]
                },
                "assumption": "Parallel pre-trends must be assessed separately.",
            }

    if eligibility["methods"]["counterfactual"]["status"] == "eligible":
        predictors = design.get("predictor_columns") or []
        for column in predictors:
            df[column] = pd.to_numeric(df[column], errors="coerce")
        model_df = df.dropna(subset=predictors)
        pre, post = model_df[model_df["_date"] < intervention], model_df[model_df["_date"] >= intervention]
        x_pre = np.column_stack([np.ones(len(pre)), pre[predictors].to_numpy(dtype=float)])
        beta, _ = _ols(x_pre, pre["_outcome"].to_numpy(dtype=float))
        pre_pred = x_pre @ beta
        post_pred = np.column_stack([np.ones(len(post)), post[predictors].to_numpy(dtype=float)]) @ beta
        results["counterfactual"] = {
            "status": "completed",
            "average_gap": float(np.mean(post["_outcome"].to_numpy(dtype=float) - post_pred)),
            "pre_rmse": float(np.sqrt(np.mean((pre["_outcome"].to_numpy(dtype=float) - pre_pred) ** 2))),
            "post_periods": len(post),
            "predictors": predictors[:20],
            "interpretation": "Predictive baseline extrapolated from the pre-intervention relationship; not proof of causality.",
        }
    return {
        "version": "causal_results_v1",
        "results": results,
        "blocked": not bool(results),
        "warning": "Estimates depend on design assumptions and do not independently prove causation.",
    }


def build_active_evidence_requests(
    *,
    data_contract: Optional[Dict[str, Any]],
    causal_eligibility: Dict[str, Any],
    web_sources: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    contract = data_contract or {}
    requests: List[Dict[str, Any]] = []
    base = [
        ("data_owner", bool(contract.get("data_owner")), "Confirm the accountable data owner."),
        ("row_grain", bool(contract.get("row_grain")), "Record what one row represents."),
        ("metric_definition", bool(contract.get("metric_definition") or contract.get("metric_definitions")), "Confirm the outcome metric definition."),
        ("as_of_date", bool(contract.get("as_of_date")), "Record the dataset as-of date."),
    ]
    for field, present, reason in base:
        if not present:
            requests.append({
                "id": f"request_{field}",
                "priority": "high" if field in {"row_grain", "metric_definition"} else "medium",
                "field": field,
                "reason": reason,
                "acceptable_sources": ["data owner confirmation", "data catalog", "approved contract"],
                "status": "open",
            })
    missing_causal = sorted({
        item for method in (causal_eligibility.get("methods") or {}).values()
        for item in method.get("missing") or []
    })
    for field in missing_causal:
        requests.append({
            "id": f"request_causal_{field}",
            "priority": "high",
            "field": field,
            "reason": "Required by at least one causal design before its estimator can run.",
            "acceptable_sources": ["causal study configuration", "intervention log", "control-series dataset"],
            "status": "open",
        })
    if not web_sources:
        requests.append({
            "id": "request_external_events",
            "priority": "low",
            "field": "external_event_sources",
            "reason": "Add dated external events if outside factors may explain changes.",
            "acceptable_sources": ["official publication", "approved web search", "organization event log"],
            "status": "open",
            "privacy_note": "Private dataset labels are never sent to web search automatically.",
        })
    return requests[:30]


def build_decision_assurance_packet(
    handle: DatasetHandle,
    *,
    findings: List[Dict[str, Any]],
    analytics_results: Optional[Dict[str, Any]] = None,
    data_contract: Optional[Dict[str, Any]] = None,
    web_sources: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    causal_eligibility = build_causal_eligibility(
        handle,
        data_contract=data_contract,
        analytics_results=analytics_results,
    )
    packet = {
        "version": "decision_assurance_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim_graph": build_claim_evidence_graph(
            findings, web_sources=web_sources, data_contract=data_contract
        ),
        "event_timeline": build_external_event_timeline(
            findings, web_sources=web_sources
        ),
        "causal_eligibility": causal_eligibility,
        "causal_results": run_causal_analyses(handle, causal_eligibility),
    }
    packet["confidence_matrix"] = build_truth_confidence_matrix(
        findings,
        data_contract=data_contract,
        web_sources=web_sources,
        causal_eligibility=causal_eligibility,
    )
    packet["evidence_requests"] = build_active_evidence_requests(
        data_contract=data_contract,
        causal_eligibility=causal_eligibility,
        web_sources=web_sources,
    )
    stable_packet = {
        key: value for key, value in packet.items() if key != "generated_at"
    }
    packet["packet_id"] = f"assurance_{_hash(stable_packet)}"
    return packet
