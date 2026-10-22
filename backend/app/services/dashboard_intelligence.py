"""Deterministic semantic planning and composition scoring for BI dashboards."""
from __future__ import annotations

import re
from statistics import median
from typing import Any


IDENTIFIER_ROLES = {
    "customer_id", "order_id", "document_no", "invoice_id", "line_id",
    "company_code",
}
AVERAGE_ROLES = {
    "price", "margin", "exchange_rate", "satisfaction_score",
    "resolution_time", "lead_time", "tenure",
}
MEASURE_PRIORITY = (
    "sales", "profit", "cost", "quantity", "stock_level", "stock_in",
    "stock_out", "output", "defects", "ad_spend", "clicks", "impressions",
    "price", "margin", "satisfaction_score", "resolution_time", "lead_time",
)
DIMENSION_PRIORITY = (
    "branch", "region", "product", "category", "channel", "customer",
    "country", "market", "department", "supplier", "warehouse", "status",
)
INTENT_KEYWORDS = {
    "trend": ("trend", "time", "over time", "แนวโน้ม", "รายวัน", "รายเดือน", "รายปี"),
    "ranking": ("top", "bottom", "rank", "ranking", "อันดับ", "สูงสุด", "ต่ำสุด"),
    "comparison": ("compare", "comparison", "versus", " vs ", "เปรียบเทียบ", "เทียบ"),
    "distribution": ("distribution", "mix", "share", "composition", "สัดส่วน", "กระจาย"),
    "detail": ("detail", "records", "rows", "table", "รายละเอียด", "ตาราง"),
    "anomaly": ("anomaly", "outlier", "unusual", "ผิดปกติ", "แปลก"),
    "forecast": ("forecast", "predict", "projection", "พยากรณ์", "คาดการณ์"),
}
V4_VARIANTS = {"executive", "analytical", "operational"}
V4_SECTION_LAYOUTS = {"hero", "featured", "balanced", "dense", "detail"}


def _role_rank(role: str | None, ordered: tuple[str, ...]) -> int:
    try:
        return ordered.index(str(role or ""))
    except ValueError:
        return len(ordered) + 1


def enrich_semantic_schema(
    schema: list[dict[str, Any]],
    roles: dict[str, str] | None = None,
    *,
    row_count: int = 0,
) -> list[dict[str, Any]]:
    """Add analysis-safe semantic types and aggregation recommendations."""
    reverse_roles = {
        str(column): str(role)
        for role, column in (roles or {}).items()
        if column
    }
    enriched: list[dict[str, Any]] = []
    for raw in schema:
        column = dict(raw)
        name = str(column.get("name") or "")
        role = reverse_roles.get(name) or column.get("semantic_role")
        kind = str(column.get("kind") or "text")
        distinct = int(column.get("distinct") or 0)
        identifier_name = bool(re.search(
            r"(^|[_\s-])(id|code|no|number|รหัส|เลขที่)($|[_\s-])",
            name,
            re.I,
        ))
        if kind == "date":
            semantic_type = "temporal_dimension"
            aggregation = None
        elif role in IDENTIFIER_ROLES or identifier_name:
            semantic_type = "identifier"
            aggregation = "count_distinct"
        elif kind == "number":
            semantic_type = "measure"
            aggregation = "average" if role in AVERAGE_ROLES else "sum"
        else:
            semantic_type = "categorical_dimension"
            aggregation = None
        column.update({
            "semantic_role": role,
            "semantic_type": semantic_type,
            "recommended_aggregation": aggregation,
            "semantic_confidence": 0.95 if name in reverse_roles else (0.82 if role else 0.55),
            "filter_eligible": (
                semantic_type == "temporal_dimension"
                or (
                    semantic_type == "categorical_dimension"
                    and 1 < distinct <= min(500, max(80, row_count or 80))
                )
            ),
        })
        enriched.append(column)
    return enriched


def detect_analysis_intent(
    instruction: str | None,
    schema: list[dict[str, Any]],
) -> dict[str, Any]:
    """Classify visualization goals before generating any chart candidates."""
    text = f" {(instruction or '').strip().lower()} "
    evidence: dict[str, list[str]] = {}
    explicit: list[str] = []
    for intent, keywords in INTENT_KEYWORDS.items():
        hits = [keyword for keyword in keywords if keyword in text]
        if hits:
            explicit.append(intent)
            evidence[intent] = hits[:3]

    has_dates = any(item.get("semantic_type") == "temporal_dimension" for item in schema)
    has_measures = any(item.get("semantic_type") == "measure" for item in schema)
    has_dimensions = any(
        item.get("semantic_type") == "categorical_dimension"
        and 1 < int(item.get("distinct") or 0) <= 500
        for item in schema
    )
    goals = list(explicit)
    if not goals:
        goals = ["overview"]
    if has_dates and has_measures and "trend" not in goals:
        goals.append("trend")
    if has_dimensions and "ranking" not in goals:
        goals.append("ranking")
    if has_dimensions and "comparison" not in goals:
        goals.append("comparison")
    if "detail" not in goals:
        goals.append("detail")
    primary = explicit[0] if explicit else "overview"
    return {
        "primary": primary,
        "goals": goals[:6],
        "confidence": round(0.9 if explicit else 0.72, 2),
        "evidence": evidence,
        "capabilities": {
            "temporal": has_dates,
            "measures": has_measures,
            "dimensions": has_dimensions,
        },
    }


def _chart_candidate(
    *,
    candidate_id: str,
    chart_type: str,
    dimension: dict[str, Any],
    measure: dict[str, Any] | None,
    goal: str,
    score: float,
    time_grain: str | None = None,
) -> dict[str, Any]:
    aggregation = (
        str(measure.get("recommended_aggregation") or "sum")
        if measure
        else "count"
    )
    measure_name = str(measure.get("name")) if measure else None
    dimension_name = str(dimension.get("name"))
    title_prefix = measure_name or "Records"
    return {
        "candidate_id": candidate_id,
        "goal": goal,
        "score": round(score, 2),
        "reasons": [
            f"semantic:{measure.get('semantic_role') or 'measure'}" if measure else "semantic:row_count",
            f"intent:{goal}",
            f"cardinality:{int(dimension.get('distinct') or 0)}",
        ],
        "widget": {
            "id": candidate_id,
            "kind": "chart",
            "chart_type": chart_type,
            "title": (
                f"{title_prefix} trend by {dimension_name}"
                if goal == "trend"
                else f"{title_prefix} by {dimension_name}"
            ),
            "dimension": dimension_name,
            "measure": measure_name,
            "aggregation": aggregation,
            "time_grain": time_grain,
            "limit": 10 if chart_type == "pie" else 20,
            "span": 6,
            "cross_filter": goal != "trend",
            "purpose": goal,
        },
    }


def generate_widget_candidates(
    schema: list[dict[str, Any]],
    intent: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate several valid alternatives instead of committing to one chart."""
    measures = sorted(
        (item for item in schema if item.get("semantic_type") == "measure"),
        key=lambda item: (
            _role_rank(item.get("semantic_role"), MEASURE_PRIORITY),
            -float(item.get("semantic_confidence") or 0),
            str(item.get("name")),
        ),
    )
    dates = sorted(
        (item for item in schema if item.get("semantic_type") == "temporal_dimension"),
        key=lambda item: (-float(item.get("semantic_confidence") or 0), str(item.get("name"))),
    )
    dimensions = sorted(
        (
            item for item in schema
            if item.get("semantic_type") == "categorical_dimension"
            and 1 < int(item.get("distinct") or 0) <= 500
        ),
        key=lambda item: (
            _role_rank(item.get("semantic_role"), DIMENSION_PRIORITY),
            abs(int(item.get("distinct") or 0) - 12),
            str(item.get("name")),
        ),
    )
    goal_bonus = {goal: 10 for goal in intent.get("goals") or []}
    candidates: list[dict[str, Any]] = []
    for date_index, date in enumerate(dates[:2]):
        for measure_index, measure in enumerate(measures[:3]):
            candidates.append(_chart_candidate(
                candidate_id=f"trend-{date_index}-{measure_index}",
                chart_type="line" if measure_index == 0 else "area",
                dimension=date,
                measure=measure,
                goal="trend",
                score=82 + goal_bonus.get("trend", 0) - measure_index * 4 - date_index * 3,
                time_grain="month",
            ))
    for dimension_index, dimension in enumerate(dimensions[:6]):
        selected_measures = measures[:2] or [None]
        for measure_index, measure in enumerate(selected_measures):
            cardinality = int(dimension.get("distinct") or 0)
            candidates.append(_chart_candidate(
                candidate_id=f"ranking-{dimension_index}-{measure_index}",
                chart_type="bar",
                dimension=dimension,
                measure=measure,
                goal="ranking",
                score=78 + goal_bonus.get("ranking", 0) - dimension_index * 2 - measure_index * 4,
            ))
            if measure_index == 0 and 2 <= cardinality <= 10:
                candidates.append(_chart_candidate(
                    candidate_id=f"mix-{dimension_index}",
                    chart_type="pie",
                    dimension=dimension,
                    measure=measure,
                    goal="distribution",
                    score=67 + goal_bonus.get("distribution", 0) - max(0, cardinality - 6),
                ))
            elif measure_index == 0 and measure is not None and 10 < cardinality <= 80:
                candidates.append(_chart_candidate(
                    candidate_id=f"pareto-{dimension_index}",
                    chart_type="pareto",
                    dimension=dimension,
                    measure=measure,
                    goal="distribution",
                    score=76 + goal_bonus.get("distribution", 0) - dimension_index * 2,
                ))
    return sorted(candidates, key=lambda item: item["score"], reverse=True)


def score_dashboard_spec(
    spec: dict[str, Any],
    schema: list[dict[str, Any]],
    intent: dict[str, Any],
) -> dict[str, Any]:
    """Score semantic fit, intent coverage, diversity and readability."""
    by_name = {str(item.get("name")): item for item in schema}
    widgets = [item for item in spec.get("widgets") or [] if item.get("kind") == "chart"]
    if not widgets:
        return {"score": 0.0, "coverage": [], "penalties": ["no_charts"]}
    score = 42.0
    coverage: set[str] = set()
    penalties: list[str] = []
    signatures: set[tuple[Any, ...]] = set()
    chart_types: set[str] = set()
    dimensions: set[str] = set()
    for widget in widgets:
        dimension = by_name.get(str(widget.get("dimension")), {})
        measure = by_name.get(str(widget.get("measure")), {})
        chart_type = str(widget.get("chart_type") or "")
        signature = (chart_type, widget.get("dimension"), widget.get("measure"), widget.get("aggregation"))
        if signature in signatures:
            score -= 12
            penalties.append("duplicate_chart")
        signatures.add(signature)
        chart_types.add(chart_type)
        dimensions.add(str(widget.get("dimension") or ""))
        if chart_type in {"line", "area"}:
            if dimension.get("semantic_type") == "temporal_dimension":
                score += 8
                coverage.add("trend")
            else:
                score -= 16
                penalties.append("non_temporal_trend")
        elif chart_type in {"bar", "pareto"}:
            score += 5
            coverage.update({"ranking", "comparison"})
            if chart_type == "pareto":
                coverage.add("distribution")
        elif chart_type == "pie":
            cardinality = int(dimension.get("distinct") or 0)
            if 2 <= cardinality <= 10:
                score += 3
                coverage.add("distribution")
            else:
                score -= 14
                penalties.append("unreadable_pie")
        if measure.get("semantic_type") == "identifier":
            score -= 25
            penalties.append("identifier_aggregation")
        elif measure.get("semantic_type") == "measure":
            score += 3
    if any(item.get("kind") == "table" for item in spec.get("widgets") or []):
        coverage.add("detail")
        score += 3
    requested = set(intent.get("goals") or [])
    score += min(18, len(requested & coverage) * 5)
    score += min(8, max(0, len(chart_types) - 1) * 3)
    score += min(6, max(0, len(dimensions) - 1) * 2)
    if len(widgets) > 8:
        score -= (len(widgets) - 8) * 3
        penalties.append("too_many_charts")
    return {
        "score": round(max(0.0, min(100.0, score)), 2),
        "coverage": sorted(coverage),
        "penalties": sorted(set(penalties)),
    }


def score_v4_presentation(spec: dict[str, Any]) -> dict[str, Any]:
    """Judge V4 page structure independently from chart semantics."""
    score = 100.0
    penalties: list[str] = []
    widgets = [item for item in spec.get("widgets") or [] if isinstance(item, dict)]
    widget_ids = {str(item.get("id")) for item in widgets}
    sections = [item for item in spec.get("sections") or [] if isinstance(item, dict)]
    assigned = [str(value) for section in sections for value in section.get("widget_ids") or []]
    if int(spec.get("version") or 0) != 4:
        score -= 20
        penalties.append("legacy_schema")
    if not sections:
        score -= 30
        penalties.append("missing_sections")
    if set(assigned) != widget_ids:
        score -= 20
        penalties.append("incomplete_widget_assignment")
    if len(assigned) != len(set(assigned)):
        score -= 20
        penalties.append("duplicate_widget_assignment")
    overview = next((item for item in sections if item.get("purpose") == "overview"), None)
    if spec.get("kpis") and not (overview and overview.get("kpi_indices")):
        score -= 10
        penalties.append("missing_kpi_hero")
    for section in sections:
        if section.get("layout") == "featured" and len(section.get("widget_ids") or []) > 1:
            score -= 8
            penalties.append("overloaded_featured_section")
    presentation = spec.get("presentation") or {}
    if presentation.get("variant") not in V4_VARIANTS:
        score -= 10
        penalties.append("invalid_variant")
    if (spec.get("story") or {}).get("mode") != "evidence_grounded":
        score -= 15
        penalties.append("ungrounded_story_contract")
    return {
        "score": round(max(0.0, min(100.0, score)), 2),
        "penalties": sorted(set(penalties)),
    }


def judge_dashboard_quality(
    spec: dict[str, Any],
    schema: list[dict[str, Any]],
    intent: dict[str, Any],
) -> dict[str, Any]:
    semantic = score_dashboard_spec(spec, schema, intent)
    presentation = score_v4_presentation(spec)
    return {
        "score": round(semantic["score"] * 0.8 + presentation["score"] * 0.2, 2),
        "semantic": semantic,
        "presentation": presentation,
    }


def apply_chart_guardrails(
    spec: dict[str, Any],
    schema: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Correct unsafe chart choices and remove charts that cannot be truthful."""
    guarded = {**spec, "widgets": []}
    by_name = {str(item.get("name")): item for item in schema}
    decisions: list[dict[str, Any]] = []
    signatures: set[tuple[Any, ...]] = set()
    chart_count = 0
    for raw in spec.get("widgets") or []:
        widget = dict(raw)
        if widget.get("kind") != "chart":
            guarded["widgets"].append(widget)
            continue
        widget_id = str(widget.get("id") or "")
        dimension = by_name.get(str(widget.get("dimension") or ""), {})
        measure = by_name.get(str(widget.get("measure") or ""), {})
        distinct = int(dimension.get("distinct") or 0)
        if distinct <= 1:
            decisions.append({
                "code": "constant_dimension_removed",
                "widget_id": widget_id,
                "action": "removed",
                "reason": "The dimension has fewer than two distinct values.",
            })
            continue
        if (
            widget.get("aggregation") in {"sum", "average"}
            and measure.get("semantic_type") == "identifier"
        ):
            decisions.append({
                "code": "identifier_aggregation_removed",
                "widget_id": widget_id,
                "action": "removed",
                "reason": "Identifiers cannot be summed or averaged truthfully.",
            })
            continue
        chart_type = str(widget.get("chart_type") or "")
        if chart_type in {"line", "area"} and dimension.get("semantic_type") != "temporal_dimension":
            widget["chart_type"] = "bar"
            widget["time_grain"] = None
            widget["purpose"] = "comparison"
            decisions.append({
                "code": "non_temporal_trend_corrected",
                "widget_id": widget_id,
                "action": "converted_to_bar",
                "reason": "Line and area charts require a temporal dimension.",
            })
        if chart_type == "pie" and distinct > 10:
            widget["chart_type"] = "bar"
            widget["limit"] = min(20, int(widget.get("limit") or 20))
            widget["purpose"] = "ranking"
            decisions.append({
                "code": "high_cardinality_pie_corrected",
                "widget_id": widget_id,
                "action": "converted_to_bar",
                "reason": "More than ten categories makes a pie chart hard to compare.",
            })
        signature = (
            widget.get("chart_type"),
            widget.get("dimension"),
            widget.get("measure"),
            widget.get("aggregation"),
            widget.get("time_grain"),
        )
        if signature in signatures:
            decisions.append({
                "code": "duplicate_chart_removed",
                "widget_id": widget_id,
                "action": "removed",
                "reason": "An equivalent chart is already present.",
            })
            continue
        if chart_count >= 8:
            decisions.append({
                "code": "chart_budget_enforced",
                "widget_id": widget_id,
                "action": "removed",
                "reason": "Decision dashboards are limited to eight charts for readability.",
            })
            continue
        signatures.add(signature)
        chart_count += 1
        guarded["widgets"].append(widget)
    return guarded, decisions


def build_decision_insights(
    computed: dict[str, Any],
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    """Derive evidence-backed driver, anomaly candidate and next-action cards."""
    spec_widgets = {str(item.get("id")): item for item in spec.get("widgets") or []}
    insights: list[dict[str, Any]] = []
    strongest_driver: dict[str, Any] | None = None
    strongest_movement: dict[str, Any] | None = None
    for result in computed.get("widgets") or []:
        widget = spec_widgets.get(str(result.get("id")), result)
        rows = list(result.get("data") or [])
        if widget.get("kind") != "chart" or not rows:
            continue
        values = [float(row["value"]) for row in rows if isinstance(row.get("value"), (int, float))]
        if not values:
            continue
        if widget.get("purpose") in {"ranking", "comparison", "distribution"}:
            total = sum(abs(value) for value in values)
            top = max(rows, key=lambda row: abs(float(row.get("value") or 0)))
            share = abs(float(top.get("value") or 0)) / total * 100 if total else 0.0
            candidate = {
                "widget_id": widget.get("id"),
                "name": top.get("name"),
                "value": top.get("value"),
                "share": round(share, 2),
                "measure": widget.get("measure") or "records",
                "dimension": widget.get("dimension"),
            }
            if strongest_driver is None or candidate["share"] > strongest_driver["share"]:
                strongest_driver = candidate
        if widget.get("purpose") == "trend" and len(rows) >= 3:
            ordered = [
                (row.get("name"), float(row["value"]))
                for row in rows
                if isinstance(row.get("value"), (int, float))
            ]
            changes: list[dict[str, Any]] = []
            for index in range(1, len(ordered)):
                previous = ordered[index - 1][1]
                current = ordered[index][1]
                if previous == 0:
                    continue
                changes.append({
                    "period": ordered[index][0],
                    "previous_period": ordered[index - 1][0],
                    "change_pct": (current - previous) / abs(previous) * 100,
                    "value": current,
                    "widget_id": widget.get("id"),
                    "measure": widget.get("measure") or "records",
                })
            if changes:
                absolute_changes = [abs(item["change_pct"]) for item in changes]
                center = median(absolute_changes)
                deviations = [abs(value - center) for value in absolute_changes]
                mad = median(deviations) if deviations else 0.0
                largest = max(changes, key=lambda item: abs(item["change_pct"]))
                distance_from_typical = abs(abs(largest["change_pct"]) - center)
                largest["is_anomaly_candidate"] = bool(
                    abs(largest["change_pct"]) >= 20
                    and (
                        (mad > 0 and distance_from_typical / mad >= 3)
                        or (mad == 0 and distance_from_typical >= 20)
                    )
                )
                if strongest_movement is None or abs(largest["change_pct"]) > abs(strongest_movement["change_pct"]):
                    strongest_movement = largest
    if strongest_driver:
        insights.append({
            "kind": "driver",
            "severity": "info",
            "title": "Leading business driver",
            "title_th": "ตัวขับเคลื่อนหลัก",
            "summary": (
                f"{strongest_driver['name']} contributes {strongest_driver['share']:.1f}% "
                f"of {strongest_driver['measure']} in this view."
            ),
            "summary_th": (
                f"{strongest_driver['name']} คิดเป็น {strongest_driver['share']:.1f}% "
                f"ของ {strongest_driver['measure']} ในมุมมองนี้"
            ),
            "evidence": strongest_driver,
        })
    if strongest_movement:
        change = strongest_movement["change_pct"]
        insights.append({
            "kind": "anomaly" if strongest_movement["is_anomaly_candidate"] else "movement",
            "severity": "warning" if strongest_movement["is_anomaly_candidate"] else "info",
            "title": "Potential anomaly to review" if strongest_movement["is_anomaly_candidate"] else "Largest period movement",
            "title_th": "ความผิดปกติที่ควรตรวจสอบ" if strongest_movement["is_anomaly_candidate"] else "การเปลี่ยนแปลงสูงสุดระหว่างช่วง",
            "summary": (
                f"{strongest_movement['measure']} changed {change:+.1f}% at "
                f"{strongest_movement['period']} versus {strongest_movement['previous_period']}."
            ),
            "summary_th": (
                f"{strongest_movement['measure']} เปลี่ยนแปลง {change:+.1f}% ในช่วง "
                f"{strongest_movement['period']} เทียบกับ {strongest_movement['previous_period']}"
            ),
            "evidence": strongest_movement,
        })
    if strongest_movement or strongest_driver:
        evidence = strongest_movement or strongest_driver or {}
        if strongest_movement:
            action = "Validate the source rows and business events behind the largest period movement."
        else:
            action = "Review the leading category and compare it with the next-ranked contributors."
        insights.append({
            "kind": "action",
            "severity": "action",
            "title": "Recommended next check",
            "title_th": "สิ่งที่แนะนำให้ตรวจต่อ",
            "summary": action,
            "summary_th": (
                "ตรวจสอบแถวข้อมูลต้นทางและเหตุการณ์ธุรกิจเบื้องหลังการเปลี่ยนแปลงสูงสุด"
                if strongest_movement
                else "ตรวจสอบหมวดหมู่ที่นำและเปรียบเทียบกับหมวดหมู่ลำดับถัดไป"
            ),
            "evidence": evidence,
        })
    return insights[:3]


def _section(
    section_id: str,
    title: str,
    purpose: str,
    layout: str,
    widget_ids: list[str],
    *,
    subtitle: str = "",
    kpi_indices: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "id": section_id,
        "title": title,
        "subtitle": subtitle,
        "purpose": purpose,
        "layout": layout,
        "widget_ids": widget_ids,
        "kpi_indices": kpi_indices or [],
    }


def build_v4_sections(
    widgets: list[dict[str, Any]],
    kpis: list[dict[str, Any]],
    *,
    variant: str = "executive",
) -> list[dict[str, Any]]:
    """Create a narrative page structure while keeping widgets independently editable."""
    variant = variant if variant in V4_VARIANTS else "executive"
    by_purpose: dict[str, list[str]] = {}
    for widget in widgets:
        purpose = str(widget.get("purpose") or ("detail" if widget.get("kind") == "table" else "comparison"))
        by_purpose.setdefault(purpose, []).append(str(widget.get("id")))
    trend_ids = by_purpose.get("trend", [])
    driver_ids = [
        *by_purpose.get("ranking", []),
        *by_purpose.get("comparison", []),
        *by_purpose.get("distribution", []),
    ]
    detail_ids = by_purpose.get("detail", [])
    assigned = set(trend_ids + driver_ids + detail_ids)
    other_ids = [str(item.get("id")) for item in widgets if str(item.get("id")) not in assigned]
    if variant == "operational":
        sections = [
            _section("overview", "Operational pulse", "overview", "hero", [], kpi_indices=list(range(len(kpis)))),
            _section("monitor", "Current movement", "trend", "dense", [*trend_ids, *other_ids]),
            _section("exceptions", "Drivers and exceptions", "drivers", "dense", driver_ids),
            _section("records", "Operational detail", "detail", "detail", detail_ids),
        ]
    elif variant == "analytical":
        sections = [
            _section("overview", "Analytical overview", "overview", "hero", [], kpi_indices=list(range(len(kpis)))),
            _section("trends", "How performance changed", "trend", "balanced", trend_ids),
            _section("drivers", "What explains the result", "drivers", "balanced", [*driver_ids, *other_ids]),
            _section("records", "Evidence and detail", "detail", "detail", detail_ids),
        ]
    else:
        sections = [
            _section("overview", "Executive summary", "overview", "hero", [], kpi_indices=list(range(len(kpis)))),
            _section("headline", "The headline movement", "trend", "featured", trend_ids[:1]),
            _section("drivers", "Key business drivers", "drivers", "balanced", [*driver_ids, *trend_ids[1:], *other_ids]),
            _section("records", "Supporting detail", "detail", "detail", detail_ids),
        ]
    return [
        item for item in sections
        if item["purpose"] == "overview" or item["widget_ids"]
    ]


def upgrade_dashboard_spec_v4(
    spec: dict[str, Any],
    *,
    variant: str | None = None,
) -> dict[str, Any]:
    """Upgrade V3/partial V4 specs into a bounded, backwards-compatible V4 DSL."""
    widgets = [dict(item) for item in spec.get("widgets") or [] if isinstance(item, dict)]
    kpis = [dict(item) for item in spec.get("kpis") or [] if isinstance(item, dict)]
    requested_presentation = spec.get("presentation") if isinstance(spec.get("presentation"), dict) else {}
    selected_variant = str(variant or requested_presentation.get("variant") or "executive")
    if selected_variant not in V4_VARIANTS:
        selected_variant = "executive"
    widget_ids = {str(item.get("id")) for item in widgets}
    raw_sections = spec.get("sections") if isinstance(spec.get("sections"), list) else []
    sections: list[dict[str, Any]] = []
    assigned: set[str] = set()
    for index, raw in enumerate(raw_sections[:12]):
        if not isinstance(raw, dict):
            continue
        section_id = re.sub(r"[^a-zA-Z0-9_-]", "-", str(raw.get("id") or f"section-{index}"))[:80]
        layout = str(raw.get("layout") or "balanced")
        layout = layout if layout in V4_SECTION_LAYOUTS else "balanced"
        ids = []
        for value in raw.get("widget_ids") or []:
            widget_id = str(value)
            if widget_id in widget_ids and widget_id not in assigned:
                ids.append(widget_id)
                assigned.add(widget_id)
        kpi_indices = [
            int(value) for value in raw.get("kpi_indices") or []
            if str(value).isdigit() and 0 <= int(value) < len(kpis)
        ][:6]
        sections.append({
            "id": section_id or f"section-{index}",
            "title": str(raw.get("title") or "Analysis")[:160],
            "subtitle": str(raw.get("subtitle") or "")[:300],
            "purpose": str(raw.get("purpose") or "analysis")[:40],
            "layout": layout,
            "widget_ids": ids,
            "kpi_indices": kpi_indices,
        })
    if not sections:
        sections = build_v4_sections(widgets, kpis, variant=selected_variant)
        assigned = {widget_id for item in sections for widget_id in item["widget_ids"]}
    missing = [item for item in widgets if str(item.get("id")) not in assigned]
    for widget in missing:
        purpose = str(widget.get("purpose") or ("detail" if widget.get("kind") == "table" else "drivers"))
        target_purposes = (
            {"detail"} if purpose == "detail"
            else {"trend"} if purpose == "trend"
            else {"drivers", "analysis"}
        )
        target = next((item for item in sections if item["purpose"] in target_purposes), None)
        if target is None:
            target = (
                _section("records", "Supporting detail", "detail", "detail", [])
                if purpose == "detail"
                else _section("analysis", "Analysis", "trend" if purpose == "trend" else "analysis", "balanced", [])
            )
            sections.append(target)
        target["widget_ids"].append(str(widget.get("id")))
    story = spec.get("story") if isinstance(spec.get("story"), dict) else {}
    default_palettes = {
        "executive": ["#0f766e", "#7c3aed", "#d97706", "#2563eb", "#dc2626"],
        "analytical": ["#2563eb", "#0891b2", "#7c3aed", "#059669", "#d97706"],
        "operational": ["#d97706", "#2563eb", "#059669", "#dc2626", "#64748b"],
    }
    requested_palette = [
        str(color).lower() for color in requested_presentation.get("palette") or []
        if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(color))
    ][:8]
    return {
        **spec,
        "version": 4,
        "presentation": {
            "variant": selected_variant,
            "theme": str(requested_presentation.get("theme") or "editorial")[:40],
            "density": str(requested_presentation.get("density") or ("compact" if selected_variant == "operational" else "comfortable"))[:40],
            "palette": requested_palette or default_palettes[selected_variant],
            "show_story": bool(requested_presentation.get("show_story", True)),
            "show_evidence": bool(requested_presentation.get("show_evidence", True)),
        },
        "sections": sections,
        "story": {
            "mode": "evidence_grounded",
            "tone": str(story.get("tone") or ("executive" if selected_variant == "executive" else "analytical"))[:40],
            "chapter_order": [item["id"] for item in sections],
        },
    }


def build_grounded_story(
    *,
    title: str,
    computed: dict[str, Any],
    spec: dict[str, Any],
    insights: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build narrative only from verified KPI/widget/insight evidence references."""
    evidence: list[dict[str, Any]] = [{
        "id": "context:query",
        "kind": "query_context",
        **(context or {}),
        "applied_filters": computed.get("applied_filters") or {},
        "filtered_row_count": computed.get("filtered_row_count"),
    }]
    for index, kpi in enumerate(computed.get("kpis") or []):
        evidence.append({
            "id": f"kpi:{index}",
            "kind": "kpi",
            "label": kpi.get("label"),
            "value": kpi.get("value"),
            "formula": "COUNT(*)" if kpi.get("kind") == "count" else f"{str(kpi.get('kind') or '').upper()}({kpi.get('field')})",
        })
    for widget in computed.get("widgets") or []:
        rows = list(widget.get("data") or [])
        evidence.append({
            "id": f"widget:{widget.get('id')}",
            "kind": "widget",
            "widget_id": widget.get("id"),
            "points": len(rows),
            "preview": rows[:3],
        })
    for index, insight in enumerate(insights):
        evidence.append({
            "id": f"insight:{index}",
            "kind": insight.get("kind"),
            "summary": insight.get("summary"),
            "summary_th": insight.get("summary_th"),
            "source_widget_id": (insight.get("evidence") or {}).get("widget_id"),
        })
    headline_insight = next((item for item in insights if item.get("kind") in {"anomaly", "movement", "driver"}), None)
    driver = next((item for item in insights if item.get("kind") == "driver"), None)
    action = next((item for item in insights if item.get("kind") == "action"), None)
    headline = headline_insight.get("summary") if headline_insight else f"Verified overview for {title}"
    headline_th = headline_insight.get("summary_th") if headline_insight else f"ภาพรวมที่ตรวจสอบแล้วของ {title}"
    summary_parts = [item.get("summary") for item in (driver, action) if item and item.get("summary")]
    summary_parts_th = [item.get("summary_th") for item in (driver, action) if item and item.get("summary_th")]
    chapters = []
    for section in spec.get("sections") or []:
        refs = [f"widget:{widget_id}" for widget_id in section.get("widget_ids") or []]
        refs.extend(f"kpi:{index}" for index in section.get("kpi_indices") or [])
        chapters.append({
            "id": section.get("id"),
            "title": section.get("title"),
            "purpose": section.get("purpose"),
            "evidence_ids": refs,
        })
    return {
        "mode": "evidence_grounded",
        "headline": headline,
        "headline_th": headline_th,
        "summary": " ".join(summary_parts) or "All statements on this page are linked to verified aggregates.",
        "summary_th": " ".join(summary_parts_th) or "ข้อความทั้งหมดในหน้านี้เชื่อมกับ Aggregate ที่ตรวจสอบแล้ว",
        "evidence_ids": [item["id"] for item in evidence],
        "chapters": chapters,
        "evidence": evidence,
    }


def build_dashboard_plan(
    *,
    title: str,
    schema: list[dict[str, Any]],
    instruction: str | None = None,
) -> dict[str, Any]:
    """Build and rank multiple complete dashboard compositions."""
    if not all(item.get("semantic_type") for item in schema):
        declared_roles = {
            str(item.get("semantic_role")): str(item.get("name"))
            for item in schema
            if item.get("semantic_role") and item.get("name")
        }
        schema = enrich_semantic_schema(schema, declared_roles)
    intent = detect_analysis_intent(instruction or title, schema)
    widget_candidates = generate_widget_candidates(schema, intent)
    measures = [item for item in schema if item.get("semantic_type") == "measure"]
    measures.sort(key=lambda item: _role_rank(item.get("semantic_role"), MEASURE_PRIORITY))
    filters = [
        {"field": item["name"], "kind": item["kind"]}
        for item in schema if item.get("filter_eligible")
    ][:5]
    kpis = [{"kind": "count", "label": "Rows", "field": None}]
    for measure in measures[:3]:
        aggregation = str(measure.get("recommended_aggregation") or "sum")
        kpis.append({
            "kind": aggregation,
            "label": f"{'Average' if aggregation == 'average' else 'Total'} {measure['name']}",
            "field": measure["name"],
        })
    detail = {
        "id": "detail",
        "kind": "table",
        "title": "Detail",
        "columns": [item["name"] for item in schema[:10]],
        "span": 12,
        "purpose": "detail",
    }

    def compose(name: str, variant: str, preferred_goals: tuple[str, ...]) -> dict[str, Any]:
        chosen: list[dict[str, Any]] = []
        used_pairs: set[tuple[Any, Any]] = set()
        for goal in preferred_goals:
            for candidate in widget_candidates:
                widget = candidate["widget"]
                pair = (widget.get("dimension"), widget.get("measure"))
                if candidate["goal"] != goal or pair in used_pairs:
                    continue
                chosen.append(dict(widget))
                used_pairs.add(pair)
                break
        for candidate in widget_candidates:
            if len(chosen) >= 5:
                break
            widget = candidate["widget"]
            pair = (widget.get("dimension"), widget.get("measure"))
            if pair not in used_pairs:
                chosen.append(dict(widget))
                used_pairs.add(pair)
        spec = upgrade_dashboard_spec_v4({
            "version": 4,
            "title": title or "Adaptive dashboard",
            "filters": filters,
            "kpis": kpis[:4],
            "widgets": [*chosen, detail],
            "presentation": {"variant": variant},
        }, variant=variant)
        judged = judge_dashboard_quality(spec, schema, intent)
        return {
            "name": name,
            "variant": variant,
            "spec": spec,
            "score": judged["score"],
            "coverage": judged["semantic"]["coverage"],
            "penalties": [
                *judged["semantic"]["penalties"],
                *judged["presentation"]["penalties"],
            ],
            "quality": judged,
        }

    compositions = [
        compose("executive_story", "executive", ("trend", "ranking", "distribution")),
        compose("analytical_deep_dive", "analytical", ("ranking", "trend", "ranking")),
        compose("operational_monitoring", "operational", ("trend", "ranking", "comparison")),
    ]
    compositions.sort(key=lambda item: item["score"], reverse=True)
    selected = compositions[0]
    return {
        "spec": selected["spec"],
        "intent": intent,
        "selected_composition": selected["name"],
        "selected_score": selected["score"],
        "composition_candidates": [
            {
                "name": item["name"],
                "variant": item["variant"],
                "score": item["score"],
                "coverage": item["coverage"],
                "penalties": item["penalties"],
                "quality": item["quality"],
            }
            for item in compositions
        ],
        "design_candidates": [
            {
                "name": item["name"],
                "variant": item["variant"],
                "score": item["score"],
                "coverage": item["coverage"],
                "quality": item["quality"],
                "spec": item["spec"],
            }
            for item in compositions
        ],
        "widget_candidates_evaluated": len(widget_candidates),
    }
