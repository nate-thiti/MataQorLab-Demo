from app.services.dashboard_intelligence import (
    apply_chart_guardrails,
    build_decision_insights,
    build_grounded_story,
    build_dashboard_plan,
    detect_analysis_intent,
    enrich_semantic_schema,
    generate_widget_candidates,
    judge_dashboard_quality,
    score_dashboard_spec,
    score_v4_presentation,
    upgrade_dashboard_spec_v4,
)


def _sales_schema():
    raw = [
        {"name": "order_date", "kind": "date", "distinct": 24, "options": []},
        {"name": "order_id", "kind": "number", "distinct": 1000, "options": []},
        {"name": "branch", "kind": "text", "distinct": 8, "options": []},
        {"name": "category", "kind": "text", "distinct": 6, "options": []},
        {"name": "customer", "kind": "text", "distinct": 120, "options": []},
        {"name": "channel", "kind": "text", "distinct": 25, "options": []},
        {"name": "revenue", "kind": "number", "distinct": 800, "options": []},
        {"name": "unit_price", "kind": "number", "distinct": 200, "options": []},
    ]
    return enrich_semantic_schema(
        raw,
        {
            "date": "order_date",
            "order_id": "order_id",
            "branch": "branch",
            "category": "category",
            "customer": "customer",
            "channel": "channel",
            "sales": "revenue",
            "price": "unit_price",
        },
        row_count=1000,
    )


def test_semantic_profile_blocks_identifiers_and_recommends_business_aggregations():
    schema = _sales_schema()
    by_name = {item["name"]: item for item in schema}

    assert by_name["order_id"]["semantic_type"] == "identifier"
    assert by_name["order_id"]["recommended_aggregation"] == "count_distinct"
    assert by_name["revenue"]["recommended_aggregation"] == "sum"
    assert by_name["unit_price"]["recommended_aggregation"] == "average"
    assert by_name["branch"]["filter_eligible"] is True


def test_analysis_intent_understands_thai_and_adds_supported_decision_goals():
    intent = detect_analysis_intent(
        "ขอดูแนวโน้มยอดขายรายเดือนและอันดับสาขาสูงสุด",
        _sales_schema(),
    )

    assert intent["primary"] == "trend"
    assert {"trend", "ranking", "detail"}.issubset(intent["goals"])
    assert intent["confidence"] >= 0.9


def test_candidate_engine_evaluates_multiple_charts_and_compositions():
    schema = _sales_schema()
    intent = detect_analysis_intent("sales decision overview", schema)
    widgets = generate_widget_candidates(schema, intent)
    plan = build_dashboard_plan(
        title="Sales intelligence",
        schema=schema,
        instruction="compare trends, ranking and category mix",
    )

    assert len(widgets) >= 8
    assert len(plan["composition_candidates"]) == 3
    assert len(plan["design_candidates"]) == 3
    assert plan["spec"]["version"] == 4
    assert plan["spec"]["sections"]
    assert plan["spec"]["story"]["mode"] == "evidence_grounded"
    assert plan["widget_candidates_evaluated"] >= 8
    assert plan["selected_score"] >= 70
    chart_widgets = [
        item for item in plan["spec"]["widgets"] if item["kind"] == "chart"
    ]
    assert any(item["chart_type"] in {"line", "area"} for item in chart_widgets)
    assert any(item["chart_type"] == "bar" for item in chart_widgets)
    assert all(item.get("measure") != "order_id" for item in chart_widgets)
    price_widgets = [item for item in chart_widgets if item.get("measure") == "unit_price"]
    assert all(item["aggregation"] == "average" for item in price_widgets)
    assert any(item["widget"]["chart_type"] == "pareto" for item in widgets)


def test_scoring_rejects_identifier_sum_and_non_temporal_line_chart():
    schema = _sales_schema()
    intent = detect_analysis_intent("show trend", schema)
    good = {
        "widgets": [{
            "id": "trend",
            "kind": "chart",
            "chart_type": "line",
            "dimension": "order_date",
            "measure": "revenue",
            "aggregation": "sum",
        }],
    }
    bad = {
        "widgets": [{
            "id": "bad",
            "kind": "chart",
            "chart_type": "line",
            "dimension": "branch",
            "measure": "order_id",
            "aggregation": "sum",
        }],
    }

    good_score = score_dashboard_spec(good, schema, intent)
    bad_score = score_dashboard_spec(bad, schema, intent)

    assert good_score["score"] > bad_score["score"]
    assert "identifier_aggregation" in bad_score["penalties"]
    assert "non_temporal_trend" in bad_score["penalties"]


def test_chart_guardrails_correct_or_remove_misleading_choices():
    schema = _sales_schema()
    spec = {
        "widgets": [
            {
                "id": "identifier-sum",
                "kind": "chart",
                "chart_type": "bar",
                "dimension": "branch",
                "measure": "order_id",
                "aggregation": "sum",
            },
            {
                "id": "wrong-line",
                "kind": "chart",
                "chart_type": "line",
                "dimension": "branch",
                "measure": "revenue",
                "aggregation": "sum",
            },
            {
                "id": "dense-pie",
                "kind": "chart",
                "chart_type": "pie",
                "dimension": "customer",
                "measure": "revenue",
                "aggregation": "sum",
            },
            {
                "id": "duplicate",
                "kind": "chart",
                "chart_type": "bar",
                "dimension": "branch",
                "measure": "revenue",
                "aggregation": "sum",
            },
        ],
    }

    guarded, decisions = apply_chart_guardrails(spec, schema)

    widgets = {item["id"]: item for item in guarded["widgets"]}
    assert "identifier-sum" not in widgets
    assert widgets["wrong-line"]["chart_type"] == "bar"
    assert widgets["dense-pie"]["chart_type"] == "bar"
    assert "duplicate" not in widgets
    assert {item["code"] for item in decisions} == {
        "identifier_aggregation_removed",
        "non_temporal_trend_corrected",
        "high_cardinality_pie_corrected",
        "duplicate_chart_removed",
    }


def test_decision_insights_are_derived_from_aggregate_evidence():
    spec = {
        "widgets": [
            {
                "id": "trend",
                "kind": "chart",
                "purpose": "trend",
                "measure": "revenue",
                "dimension": "order_date",
            },
            {
                "id": "ranking",
                "kind": "chart",
                "purpose": "ranking",
                "measure": "revenue",
                "dimension": "branch",
            },
        ],
    }
    computed = {
        "widgets": [
            {
                "id": "trend",
                "kind": "chart",
                "data": [
                    {"name": "Jan", "value": 100.0},
                    {"name": "Feb", "value": 105.0},
                    {"name": "Mar", "value": 110.25},
                    {"name": "Apr", "value": 220.5},
                ],
            },
            {
                "id": "ranking",
                "kind": "chart",
                "data": [
                    {"name": "North", "value": 80.0},
                    {"name": "South", "value": 20.0},
                ],
            },
        ],
    }

    insights = build_decision_insights(computed, spec)

    assert [item["kind"] for item in insights] == ["driver", "anomaly", "action"]
    assert insights[0]["evidence"]["share"] == 80.0
    assert insights[1]["evidence"]["change_pct"] == 100.0
    assert insights[1]["evidence"]["is_anomaly_candidate"] is True


def test_repeated_growth_rate_is_not_mislabeled_as_an_anomaly():
    spec = {"widgets": [{
        "id": "trend",
        "kind": "chart",
        "purpose": "trend",
        "measure": "revenue",
        "dimension": "order_date",
    }]}
    computed = {"widgets": [{
        "id": "trend",
        "kind": "chart",
        "data": [
            {"name": "Jan", "value": 100.0},
            {"name": "Feb", "value": 125.0},
            {"name": "Mar", "value": 156.25},
            {"name": "Apr", "value": 195.3125},
        ],
    }]}

    insights = build_decision_insights(computed, spec)

    assert insights[0]["kind"] == "movement"
    assert insights[0]["evidence"]["is_anomaly_candidate"] is False


def test_v4_upgrade_preserves_v3_widgets_and_assigns_each_to_one_section():
    upgraded = upgrade_dashboard_spec_v4({
        "version": 3,
        "title": "Legacy",
        "kpis": [{"kind": "count", "label": "Rows"}],
        "widgets": [
            {"id": "trend", "kind": "chart", "purpose": "trend"},
            {"id": "driver", "kind": "chart", "purpose": "ranking"},
            {"id": "detail", "kind": "table", "purpose": "detail"},
        ],
    })

    assigned = [widget_id for section in upgraded["sections"] for widget_id in section["widget_ids"]]
    assert upgraded["version"] == 4
    assert upgraded["presentation"]["variant"] == "executive"
    assert upgraded["story"]["mode"] == "evidence_grounded"
    assert assigned == ["trend", "driver", "detail"]
    assert len(assigned) == len(set(assigned))


def test_v4_story_contains_only_references_to_computed_evidence():
    spec = upgrade_dashboard_spec_v4({
        "title": "Sales",
        "kpis": [{"kind": "sum", "field": "revenue", "label": "Revenue"}],
        "widgets": [{"id": "driver", "kind": "chart", "purpose": "ranking"}],
    })
    computed = {
        "kpis": [{"kind": "sum", "field": "revenue", "label": "Revenue", "value": 100}],
        "widgets": [{"id": "driver", "kind": "chart", "data": [{"name": "A", "value": 100}]}],
    }
    insights = [{
        "kind": "driver",
        "summary": "A contributes 100% of revenue.",
        "summary_th": "A คิดเป็น 100% ของ revenue",
        "evidence": {"widget_id": "driver"},
    }]

    story = build_grounded_story(title="Sales", computed=computed, spec=spec, insights=insights)

    assert story["headline"] == insights[0]["summary"]
    assert set(story["evidence_ids"]) == {"context:query", "kpi:0", "widget:driver", "insight:0"}
    assert all(
        evidence_id in story["evidence_ids"]
        for chapter in story["chapters"]
        for evidence_id in chapter["evidence_ids"]
    )


def test_v4_quality_judge_separates_semantics_from_page_structure():
    schema = _sales_schema()
    intent = detect_analysis_intent("executive sales trend", schema)
    plan = build_dashboard_plan(title="Sales", schema=schema, instruction="executive sales trend")
    valid = plan["spec"]
    malformed = {
        **valid,
        "version": 3,
        "sections": [],
        "story": {},
    }

    valid_presentation = score_v4_presentation(valid)
    malformed_presentation = score_v4_presentation(malformed)
    valid_quality = judge_dashboard_quality(valid, schema, intent)
    malformed_quality = judge_dashboard_quality(malformed, schema, intent)

    assert valid_presentation["score"] == 100
    assert malformed_presentation["score"] < 50
    assert valid_quality["score"] > malformed_quality["score"]
    assert valid_quality["semantic"]["score"] == malformed_quality["semantic"]["score"]
