"""Deterministic semantic-mapping readiness for setup and analytical execution."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional


METRIC_ROLES = frozenset({
    "sales", "revenue", "gross_amount", "net_amount", "cost", "profit", "margin",
    "price", "quantity", "stock_level", "stock_in", "stock_out", "salary", "tenure",
    "defects", "output", "downtime", "ad_spend", "clicks", "impressions",
    "satisfaction_score", "resolution_time", "lead_time", "discount", "tax",
    "exchange_rate",
})
TEMPORAL_ROLES = frozenset({"date", "timestamp", "due_date", "year", "month"})
IDENTIFIER_ROLES = frozenset({
    "id", "order_id", "invoice_id", "line_id", "document_no", "customer_id",
    "company_code",
})
DIMENSION_ROLES = frozenset({
    "branch", "region", "country", "market", "channel", "customer", "product",
    "category", "supplier", "department", "employee", "status", "payment_status",
    "warehouse", "currency", "unit",
})
ANALYTICAL_ROLES = METRIC_ROLES | TEMPORAL_ROLES | IDENTIFIER_ROLES | DIMENSION_ROLES
ROLE_ALIASES = {
    "revenue": "sales", "income": "sales", "amount": "sales", "total": "sales",
    "value": "sales", "qty": "quantity", "units": "quantity", "timestamp": "date",
    "invoice": "invoice_id", "invoice_no": "invoice_id", "bill": "invoice_id",
    "order": "order_id", "product_code": "product", "sku": "product",
    "client": "customer", "buyer": "customer", "inventory": "stock_level",
}


def normalize_mapping(mapping: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    return {
        str(column): ROLE_ALIASES.get(str(role).strip().lower(), str(role).strip().lower())
        for column, role in (mapping or {}).items()
        if str(column).strip() and str(role or "").strip()
    }


def scan_columns(scan_result: Optional[Mapping[str, Any]]) -> list[str]:
    return [
        str(item.get("name"))
        for item in (scan_result or {}).get("columns") or []
        if isinstance(item, Mapping) and item.get("name")
    ]


def suggested_mapping_from_scan(scan_result: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    scan = scan_result or {}
    suggested = normalize_mapping(scan.get("suggested_mapping") or {})
    for item in scan.get("columns") or []:
        if not isinstance(item, Mapping) or not item.get("name"):
            continue
        role = str(item.get("suggested_role") or item.get("role") or "").strip().lower()
        if role:
            suggested.setdefault(str(item["name"]), role)
    return suggested


def required_semantic_roles(
    suggested_mapping: Optional[Mapping[str, Any]],
) -> list[str]:
    roles = set(normalize_mapping(suggested_mapping).values())
    required: list[str] = []
    priorities = (
        (
            "sales", "net_amount", "gross_amount", "stock_level", "quantity", "profit",
            "cost", "output", "salary", "ad_spend", "satisfaction_score", "defects",
            "stock_in", "stock_out", "clicks", "impressions", "lead_time",
        ),
        ("date", "due_date", "year", "month"),
        ("line_id", "order_id", "invoice_id", "document_no", "customer_id", "id"),
    )
    for priority in priorities:
        candidate = next((role for role in priority if role in roles), None)
        if candidate:
            required.append(candidate)
    if not required:
        dimensions = sorted(roles & DIMENSION_ROLES)
        if dimensions:
            required.append(dimensions[0])
    return required


def evaluate_semantic_mapping_gate(
    *,
    mapping: Optional[Mapping[str, Any]],
    data_contract: Optional[Mapping[str, Any]] = None,
    columns: Optional[Iterable[str]] = None,
    suggested_mapping: Optional[Mapping[str, Any]] = None,
    require_confirmation: bool = True,
) -> Dict[str, Any]:
    normalized = normalize_mapping(mapping)
    contract = data_contract or {}
    available = {str(column) for column in (columns or normalized.keys())}
    roles = set(normalized.values())
    missing_columns = sorted(set(normalized) - available)
    unknown_roles = sorted(role for role in roles if role not in ANALYTICAL_ROLES)
    required_roles = required_semantic_roles(suggested_mapping)
    missing_required_roles = [role for role in required_roles if role not in roles]
    metric_sources = {
        str(item.get("source_column") or "")
        for item in contract.get("metric_definitions") or []
        if isinstance(item, Mapping) and item.get("source_column")
    }
    unmapped_metric_sources = sorted(metric_sources - set(normalized))
    has_anchor = bool(roles & (METRIC_ROLES | IDENTIFIER_ROLES | DIMENSION_ROLES))
    confirmed = bool(contract.get("mapping_confirmed"))

    issues: list[Dict[str, Any]] = []
    if not normalized:
        issues.append({"code": "mapping_required", "message": "Semantic column mapping is required."})
    if require_confirmation and not confirmed:
        issues.append({"code": "mapping_confirmation_required", "message": "Semantic mapping must be confirmed by the user."})
    if missing_columns:
        issues.append({
            "code": "mapping_columns_missing",
            "message": "Mapped columns are not present in the source.",
            "fields": missing_columns[:20],
        })
    if unknown_roles:
        issues.append({
            "code": "unknown_semantic_roles",
            "message": "Mapping contains unsupported semantic roles.",
            "fields": unknown_roles[:20],
        })
    if normalized and not has_anchor:
        issues.append({
            "code": "analytical_role_required",
            "message": "Map at least one metric, identifier, or business dimension before analysis.",
        })
    if missing_required_roles:
        issues.append({
            "code": "suggested_critical_roles_unconfirmed",
            "message": "Critical roles detected from the source still require mapping.",
            "fields": missing_required_roles,
        })
    if unmapped_metric_sources:
        issues.append({
            "code": "metric_sources_unmapped",
            "message": "Every governed metric source must have a semantic mapping.",
            "fields": unmapped_metric_sources[:20],
        })

    return {
        "ready": not issues,
        "mapping": normalized,
        "roles": sorted(roles),
        "required_roles": required_roles,
        "missing_required_roles": missing_required_roles,
        "mapping_confirmed": confirmed,
        "issues": issues,
    }
