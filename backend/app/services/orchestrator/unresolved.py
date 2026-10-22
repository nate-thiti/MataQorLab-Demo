"""Convert validator/setup blockers into ONE prioritized UnresolvedDecision."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, Field

from app.services.etl_pipeline import normalize_data_contract, validate_data_contract
from app.services.orchestrator.decision_identity import (
    is_decision_confirmed,
    is_original_prompt_capture,
)
from app.services.semantic_mapping_gate import (
    evaluate_semantic_mapping_gate,
    normalize_mapping,
    suggested_mapping_from_scan,
)

# Lower number = ask first. Business meaning before governance metadata.
_PRIORITY: Dict[str, int] = {
    "row_grain": 10,
    "mapping:date": 20,
    "mapping:sales": 21,
    "mapping:quantity": 22,
    "mapping:invoice": 23,
    "mapping:product": 24,
    "mapping:customer": 25,
    "return_policy": 30,
    "primary_metric": 40,
    "metric_definition": 40,
    "reporting_period_status": 50,
    "period_status": 50,
    "business_purpose": 60,
    "data_owner": 70,
    "mapping_confirmed": 80,
    "business_context_reviewed": 90,
}

_MISSING_TO_KEY = {
    "row_grain_recorded": "row_grain",
    "metric_definition_recorded": "primary_metric",
    "business_purpose_recorded": "business_purpose",
    "data_owner_recorded": "data_owner",
    "period_status_reviewed": "reporting_period_status",
    "mapping_confirmed": "mapping_confirmed",
    "business_context_reviewed": "business_context_reviewed",
    # mapping_present is a tool concern, not a chat checklist.
}

class UnresolvedDecision(BaseModel):
    decision_key: str
    category: str = "data_contract"
    priority: int = 100
    reason: str
    evidence: Dict[str, Any] = Field(default_factory=dict)
    options: List[Dict[str, Any]] = Field(default_factory=list)
    required_for_capability: Optional[str] = None
    question_th: Optional[str] = None
    question_en: Optional[str] = None


def _scan_columns(session: Mapping[str, Any]) -> List[str]:
    scan = session.get("scan_result") or {}
    cols = []
    for item in list(scan.get("columns") or [])[:40]:
        if isinstance(item, Mapping) and item.get("name"):
            cols.append(str(item["name"]))
    return cols


def _scan_profiles(session: Mapping[str, Any]) -> List[Dict[str, Any]]:
    scan = session.get("scan_result") or {}
    return [
        dict(item)
        for item in list(scan.get("columns") or [])[:40]
        if isinstance(item, Mapping) and item.get("name")
    ]


def _role_candidates(
    profiles: List[Mapping[str, Any]],
    role: str,
    mapping: Mapping[str, str],
) -> List[str]:
    aliases = {
        "date": ("date", "time", "day", "month", "year", "วันที่", "เวลา"),
        "sales": ("sale", "revenue", "amount", "total", "net", "gross", "ยอด", "รายได้"),
        "quantity": ("qty", "quantity", "unit", "volume", "จำนวน", "ชิ้น"),
        "invoice": ("invoice", "bill", "order", "document", "เลขที่", "บิล"),
        "product": ("product", "sku", "item", "สินค้า"),
        "customer": ("customer", "client", "buyer", "ลูกค้า"),
    }.get(role, (role,))
    expected_types = {
        "date": {"date"},
        "sales": {"number"},
        "quantity": {"number"},
    }.get(role, set())

    ranked: List[tuple[int, str]] = []
    for item in profiles:
        name = str(item.get("name") or "")
        lowered = name.lower()
        suggested = str(item.get("suggested_role") or item.get("role") or "").lower()
        mapped = str(mapping.get(name) or "").lower()
        inferred = str(item.get("inferred_type") or item.get("dtype") or "").lower()
        score = 0
        if mapped == role:
            score += 100
        if suggested == role or suggested in aliases:
            score += 80
        if any(alias in lowered for alias in aliases):
            score += 35
        if inferred in expected_types:
            score += 10
        if score:
            ranked.append((score, name))
    return [name for _, name in sorted(ranked, key=lambda item: (-item[0], item[1]))[:6]]


def _metric_candidates(
    profiles: List[Mapping[str, Any]],
    mapping: Mapping[str, str],
) -> List[Dict[str, Any]]:
    metric_roles = {
        "sales": "ยอดขาย",
        "revenue": "รายได้",
        "net_amount": "ยอดสุทธิ",
        "gross_amount": "ยอดรวม",
        "profit": "กำไร",
        "cost": "ต้นทุน",
        "quantity": "จำนวน",
        "stock_level": "คงเหลือ",
        "output": "ผลผลิต",
        "spend": "ค่าใช้จ่าย",
    }
    candidates: List[Dict[str, Any]] = []
    seen = set()
    for item in profiles:
        name = str(item.get("name") or "")
        role = str(
            mapping.get(name)
            or item.get("suggested_role")
            or item.get("role")
            or ""
        ).lower()
        inferred = str(item.get("inferred_type") or item.get("dtype") or "").lower()
        if name in seen or (role not in metric_roles and inferred != "number"):
            continue
        # Unmapped numeric identifiers are poor metric suggestions.
        lowered = name.lower()
        if role not in metric_roles and any(token in lowered for token in ("id", "code", "no", "เลข")):
            continue
        seen.add(name)
        label = metric_roles.get(role, "ค่าตัวเลข")
        candidates.append({
            "id": name,
            "label": f"{label} — {name}",
            "value": name,
            "role": role,
        })
    return candidates[:4]


def _domain_options(scan: Mapping[str, Any]) -> List[Dict[str, Any]]:
    labels_th = {
        "sales": "วิเคราะห์ยอดขาย",
        "inventory": "บริหารสินค้าคงคลัง",
        "finance": "วิเคราะห์การเงิน",
        "procurement": "วิเคราะห์การจัดซื้อ",
        "hr": "วิเคราะห์ทรัพยากรบุคคล",
        "manufacturing": "วิเคราะห์การผลิต",
        "marketing": "วิเคราะห์การตลาด",
        "customer_experience": "วิเคราะห์ประสบการณ์ลูกค้า",
        "general": "วิเคราะห์ข้อมูลทั่วไป",
    }
    suggested = str(scan.get("suggested_domain") or "general")
    values = [suggested]
    for item in scan.get("domain_options") or []:
        if not isinstance(item, Mapping):
            continue
        value = str(item.get("value") or "")
        if value and value not in values and value != "other":
            values.append(value)
        if len(values) >= 3:
            break
    options = [
        {"id": value, "label": labels_th.get(value, value), "value": value}
        for value in values
    ]
    options.append({"id": "other", "label": "เป้าหมายอื่น", "value": "other"})
    return options


def _negative_count(session: Mapping[str, Any]) -> Optional[int]:
    scan = session.get("scan_result") or {}
    for key in ("negative_value_count", "negative_rows", "returns_estimate"):
        if scan.get(key) is not None:
            try:
                return int(scan.get(key))
            except (TypeError, ValueError):
                pass
    findings = scan.get("quality_findings") or scan.get("findings") or []
    for item in findings:
        if not isinstance(item, Mapping):
            continue
        kind = str(item.get("type") or item.get("code") or "").lower()
        if "negative" in kind or "return" in kind:
            try:
                return int(item.get("count") or 0)
            except (TypeError, ValueError):
                return None
    return None


def _confirmed(contract: Mapping[str, Any], key: str) -> bool:
    if key == "return_policy":
        policy = contract.get("return_policy")
        if isinstance(policy, Mapping):
            return bool(policy.get("value") or policy.get("source") == "user_confirmed")
        return bool(policy)
    if key == "primary_metric":
        return bool(contract.get("metric_definition") or contract.get("metric_definitions"))
    if key == "reporting_period_status":
        return str(contract.get("period_status") or "unknown") != "unknown"
    if key in {"mapping_confirmed", "business_context_reviewed"}:
        return bool(contract.get(key))
    return bool(str(contract.get(key) or "").strip())


def _question_for(
    key: str,
    *,
    evidence: Mapping[str, Any],
) -> tuple[str, str, List[Dict[str, Any]]]:
    cols = list(evidence.get("columns") or [])[:4]
    col_hint = " และ ".join(cols) if cols else "โครงสร้างคอลัมน์"
    negatives = evidence.get("negative_count")

    metric_candidates = list(evidence.get("metric_candidates") or [])
    domain = str(evidence.get("suggested_domain") or "general")
    domain_labels = {
        "sales": "ยอดขาย",
        "inventory": "สินค้าคงคลัง",
        "finance": "การเงิน",
        "procurement": "การจัดซื้อ",
        "hr": "ทรัพยากรบุคคล",
        "manufacturing": "การผลิต",
        "marketing": "การตลาด",
        "customer_experience": "ประสบการณ์ลูกค้า",
        "general": "ข้อมูลธุรกิจทั่วไป",
    }
    negative_column = cols[0] if cols else "คอลัมน์ตัวเลข"
    negative_prefix = (
        f"พบค่าติดลบ {negatives} รายการใน {negative_column} "
        if negatives is not None
        else f"พบค่าติดลบใน {negative_column} "
    )
    if domain == "inventory":
        negative_question = negative_prefix + "ค่าดังกล่าวหมายถึงการจ่าย/ตัดสต็อกออก หรือควรจัดการแบบอื่น?"
        negative_options = [
            {
                "id": "negative_is_outflow",
                "label": "เป็นการจ่ายหรือตัดสต็อกออก",
                "value": "negative_is_outflow",
                "treatment": "retain_as_outflow",
            },
            {
                "id": "exclude_negatives",
                "label": "เป็นข้อมูลผิดพลาด — ไม่นำมาวิเคราะห์",
                "value": "exclude_negatives",
                "treatment": "exclude",
            },
            {"id": "keep_as_is", "label": "คงค่าตามข้อมูลต้นทาง", "value": "keep_as_is"},
        ]
    else:
        negative_question = negative_prefix + "ค่าดังกล่าวควรถูกตีความอย่างไรในการวิเคราะห์?"
        negative_options = [
            {
                "id": "negative_is_return",
                "label": "เป็นรายการคืน/ปรับลดยอด",
                "value": "negative_is_return",
                "treatment": "retain_as_return",
            },
            {
                "id": "exclude_negatives",
                "label": "เป็นข้อมูลผิดพลาด — ไม่นำมาวิเคราะห์",
                "value": "exclude_negatives",
                "treatment": "exclude",
            },
            {"id": "keep_as_is", "label": "คงค่าตามข้อมูลต้นทาง", "value": "keep_as_is"},
        ]

    templates = {
        "row_grain": (
            f"จากคอลัมน์ {col_hint} ข้อมูลหนึ่งแถวแทนหน่วยใด?",
            f"Based on columns ({', '.join(cols) or 'schema'}), what does one row represent?",
            list(evidence.get("grain_options") or [
                {"id": "source_record", "label": "หนึ่งระเบียนจากข้อมูลต้นทาง", "value": "source_record"},
                {"id": "other", "label": "หน่วยอื่น", "value": "other"},
            ]),
        ),
        "return_policy": (
            negative_question,
            f"How should negative values in {negative_column} be interpreted?",
            negative_options,
        ),
        "primary_metric": (
            (
                "ต้องการใช้คอลัมน์ใดเป็นตัวชี้วัดหลักของการวิเคราะห์? "
                + (f"ระบบพบตัวเลือกจากข้อมูล: {', '.join(item['value'] for item in metric_candidates)}" if metric_candidates else "ยังไม่พบคอลัมน์ตัวเลขที่มีบทบาทชัดเจน")
            ),
            "Which data column should be the primary analysis metric?",
            metric_candidates + [{"id": "other", "label": "ตัวชี้วัดอื่น", "value": "other"}],
        ),
        "business_purpose": (
            f"จากโครงสร้างข้อมูล ระบบมองว่าเป็นชุดข้อมูลด้าน{domain_labels.get(domain, domain)} เป้าหมายหลักที่ต้องการวิเคราะห์คืออะไร?",
            f"The schema looks like {domain}. What is the primary analysis goal?",
            list(evidence.get("domain_options") or [{"id": "other", "label": "เป้าหมายอื่น", "value": "other"}]),
        ),
        "data_owner": (
            "ใครเป็นเจ้าของข้อมูลชุดนี้สำหรับงานวิเคราะห์นี้?",
            "Who is the accountable data owner for this analysis?",
            [
                {
                    "id": "current_user",
                    "label": "ฉันเป็นเจ้าของข้อมูลชุดนี้",
                    "value": "current_user",
                },
            ],
        ),
        "reporting_period_status": (
            f"ข้อมูลในคอลัมน์ {evidence.get('date_column') or 'วันที่'} ครบตามรอบรายงานที่ต้องการวิเคราะห์แล้วหรือยัง?",
            f"Is the reporting period in {evidence.get('date_column') or 'the date column'} complete?",
            [
                {"id": "complete", "label": "ครบแล้ว", "value": "complete"},
                {"id": "partial", "label": "ยังไม่ครบ", "value": "partial"},
                {"id": "unknown", "label": "ยังไม่ทราบ", "value": "unknown"},
            ],
        ),
        "mapping_confirmed": (
            "การจับคู่คอลัมน์สำคัญพร้อมยืนยันแล้วใช่ไหม?",
            "Can we confirm the critical column mapping?",
            [
                {"id": "approved", "label": "ยืนยัน Mapping", "value": "true"},
                {"id": "modify", "label": "ยังต้องปรับ", "value": "false"},
            ],
        ),
        "business_context_reviewed": (
            "บริบททางธุรกิจที่ยืนยันไว้พร้อมใช้วิเคราะห์แล้วใช่ไหม?",
            "Is the confirmed business context ready for analysis?",
            [
                {"id": "approved", "label": "พร้อมแล้ว", "value": "true"},
                {"id": "modify", "label": "ยังไม่พร้อม", "value": "false"},
            ],
        ),
    }
    if key.startswith("mapping:"):
        role = key.split(":", 1)[1]
        th = f"คอลัมน์ไหนคือ {role} หลักของชุดข้อมูลนี้?"
        en = f"Which column is the primary {role}?"
        opts = [
            {"id": c, "label": c, "value": c}
            for c in list(evidence.get("role_candidates") or cols)[:6]
        ]
        return th, en, opts
    item = templates.get(key)
    if not item:
        return (
            f"ต้องการยืนยัน {key} ก่อนดำเนินการต่อ",
            f"Please confirm {key} before continuing.",
            [],
        )
    return item[0], item[1], item[2]


def resolve_unresolved_decisions(
    session: Mapping[str, Any],
    *,
    required_for_capability: Optional[str] = "validate",
) -> List[UnresolvedDecision]:
    recipe = session.get("cleaning_recipe") or {}
    contract_raw = recipe.get("data_contract") if isinstance(recipe, Mapping) else {}
    contract = normalize_data_contract(contract_raw)
    # Preserve non-normalized confirmed fields.
    if isinstance(contract_raw, Mapping) and contract_raw.get("return_policy"):
        contract["return_policy"] = contract_raw.get("return_policy")
    # Repair legacy sessions affected by kickoff prose being consumed as a
    # contract answer. Keep the stored audit untouched, but treat the value as
    # unresolved so the controller asks the real question again.
    for decision_key, field in (
        ("row_grain", "row_grain"),
        ("primary_metric", "metric_definition"),
        ("business_purpose", "business_purpose"),
        ("data_owner", "data_owner"),
    ):
        if is_original_prompt_capture(session, decision_key, contract.get(field)):
            contract[field] = ""

    mapping = {
        str(k): str(v).strip().lower()
        for k, v in dict(session.get("column_mapping") or {}).items()
        if str(v or "").strip()
    }
    columns = _scan_columns(session)
    profiles = _scan_profiles(session)
    scan = session.get("scan_result") or {}
    readiness = validate_data_contract(contract, mapping, columns or list(mapping.keys()))
    missing = list(readiness.get("missing") or [])

    out: List[UnresolvedDecision] = []

    # High-impact mapping gaps only when mapping has started (avoid early spam).
    suggested_mapping = suggested_mapping_from_scan(scan)
    mapping_gate = evaluate_semantic_mapping_gate(
        mapping=mapping,
        data_contract=contract,
        columns=columns or list(mapping),
        suggested_mapping=suggested_mapping,
        require_confirmation=True,
    )
    mapped_roles = set(normalize_mapping(mapping).values())
    for role_key in mapping_gate["missing_required_roles"]:
        if role_key in mapped_roles or not columns:
            continue
        key = f"mapping:{role_key}"
        if is_decision_confirmed(session, key):
            continue
        candidates = [column for column, role in suggested_mapping.items() if role == role_key]
        evidence = {
            "columns": columns,
            "role": role_key,
            "role_candidates": candidates or _role_candidates(profiles, role_key, mapping),
        }
        th, en, opts = _question_for(key, evidence=evidence)
        out.append(UnresolvedDecision(
            decision_key=key,
            category="mapping",
            priority=_PRIORITY.get(key, 25),
            reason=f"critical_mapping_missing:{role_key}",
            evidence=evidence,
            options=opts,
            required_for_capability="map",
            question_th=th,
            question_en=en,
        ))

    neg = _negative_count(session)
    if neg and neg > 0 and not is_decision_confirmed(session, "return_policy"):
        sales_columns = _role_candidates(profiles, "sales", mapping)
        evidence = {
            "negative_count": neg,
            "columns": sales_columns or columns,
            "suggested_domain": scan.get("suggested_domain") or "general",
        }
        th, en, opts = _question_for("return_policy", evidence=evidence)
        out.append(UnresolvedDecision(
            decision_key="return_policy",
            category="data_quality",
            priority=_PRIORITY["return_policy"],
            reason="negative_transactions_need_policy",
            evidence=evidence,
            options=opts,
            required_for_capability="clean",
            question_th=th,
            question_en=en,
        ))

    for miss in missing:
        if miss == "mapping_present":
            continue  # Engine/tool concern
        key = _MISSING_TO_KEY.get(miss, miss)
        if is_decision_confirmed(session, key):
            continue
        # Skip mapping role spam if we already have many mapping:* entries —
        # grain/metric first. Cap mapping:* later via select_one.
        evidence = {
            "columns": columns,
            "missing_check": miss,
            "suggested_domain": scan.get("suggested_domain") or "general",
            "metric_candidates": _metric_candidates(profiles, mapping),
            "domain_options": _domain_options(scan),
            "date_column": next(iter(_role_candidates(profiles, "date", mapping)), None),
        }
        # Grain evidence: prefer invoice/product-like names.
        if key == "row_grain":
            grain_roles = {
                "line_id", "order_id", "invoice_id", "document_no",
                "customer_id", "product", "stock_in", "stock_out", "stock_level",
            }
            evidence["columns"] = [
                str(item.get("name"))
                for item in profiles
                if str(item.get("suggested_role") or item.get("role") or "").lower() in grain_roles
                or any(
                    tok in str(item.get("name") or "").lower()
                    for tok in ("invoice", "bill", "product", "sku", "item", "order", "movement")
                )
            ][:4] or columns[:4]
            evidence["likely_value"] = "invoice_line"
            raw_grain_options = list(scan.get("grain_options") or [])
            grain_labels = {
                "order_item": "หนึ่งรายการสินค้าในคำสั่งซื้อ/ใบแจ้งหนี้",
                "invoice_line": "หนึ่งรายการสินค้าในใบแจ้งหนี้",
                "order": "หนึ่งคำสั่งซื้อหรือใบแจ้งหนี้",
                "customer": "หนึ่งลูกค้า",
                "inventory_movement": "หนึ่งความเคลื่อนไหวของสต็อก",
                "inventory_snapshot": "หนึ่งรายการยอดคงเหลือ ณ เวลาใดเวลาหนึ่ง",
                "source_record": "หนึ่งระเบียนจากข้อมูลต้นทาง",
                "other": "หน่วยอื่น",
            }
            evidence["grain_options"] = [
                {
                    "id": str(item.get("value") or ""),
                    "label": grain_labels.get(str(item.get("value") or ""), str(item.get("label") or "")),
                    "value": str(item.get("value") or ""),
                }
                for item in raw_grain_options
                if isinstance(item, Mapping) and item.get("value")
            ]
        th, en, opts = _question_for(key, evidence=evidence)
        out.append(UnresolvedDecision(
            decision_key=key,
            category="data_contract",
            priority=_PRIORITY.get(key, 100),
            reason=f"contract_missing:{miss}",
            evidence=evidence,
            options=opts,
            required_for_capability=required_for_capability,
            question_th=th,
            question_en=en,
        ))

    # De-dupe by decision_key keeping best (lowest) priority.
    by_key: Dict[str, UnresolvedDecision] = {}
    for item in out:
        prev = by_key.get(item.decision_key)
        if prev is None or item.priority < prev.priority:
            by_key[item.decision_key] = item

    ordered = sorted(by_key.values(), key=lambda d: (d.priority, d.decision_key))
    # Prefer business meaning over flooding with mapping:* — keep at most 2 mapping
    # decisions in the queue after non-mapping items are considered by select_one.
    return ordered


def select_one_decision(
    decisions: List[UnresolvedDecision],
) -> Optional[UnresolvedDecision]:
    if not decisions:
        return None
    # Prefer non-mapping first if present.
    for item in decisions:
        if not item.decision_key.startswith("mapping:"):
            return item
    return decisions[0]


def strip_raw_validator_checklist(text: str) -> str:
    """Guard against leaking English multi-field validator prose to users."""
    lowered = (text or "").lower()
    banned = (
        "please provide",
        "missing contract",
        "data contract status",
        "complete required context",
        "validation missing",
        "data_owner_recorded",
        "row_grain_recorded",
        "metric_definition_recorded",
        "business_purpose_recorded",
        "period_status_reviewed",
    )
    if any(b in lowered for b in banned):
        return ""
    # Bullet checklist of many fields
    if text.count("\n-") >= 3 or text.count("\n•") >= 3:
        return ""
    return text
