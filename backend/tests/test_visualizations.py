import json
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.services.dataset_engine import DatasetHandle
from app.services.visualizations import (
    _build_dashboard_spec,
    _dashboard_semantic_warnings,
    _dashboard_data,
    _dashboard_cache_get,
    _dashboard_cache_key,
    _dashboard_cache_set,
    _extract_json_object,
    _normalize_dashboard_spec,
    _resolve_planner_spec,
    _sanitize_shared_dashboard_payload,
    build_visualization_proposal,
    build_chat_visualization_context,
    generate_dashboard,
    get_shared_dashboard,
    VisualizationError,
    create_report,
    list_reports,
    normalize_chart,
    update_report,
)


def test_dashboard_spec_adapts_to_dataset_schema():
    spec = _build_dashboard_spec(
        {"title": "Sales dashboard"},
        [
            {"name": "month", "kind": "date", "distinct": 12, "options": []},
            {"name": "branch", "kind": "text", "distinct": 4, "options": ["A", "B"]},
            {"name": "revenue", "kind": "number", "distinct": 30, "options": []},
        ],
    )

    assert spec["title"] == "Sales dashboard"
    assert {item["field"] for item in spec["filters"]} == {"month", "branch"}
    assert any(widget.get("chart_type") == "line" for widget in spec["widgets"])
    assert any(widget.get("chart_type") == "bar" for widget in spec["widgets"])


def test_visualization_proposal_uses_schema_without_embedding_raw_rows():
    handle = DatasetHandle.from_dataframe(
        pd.DataFrame(
            {
                "month": pd.date_range("2025-01-01", periods=12, freq="MS"),
                "branch": ["A", "B"] * 6,
                "revenue": list(range(100, 112)),
            }
        )
    )

    proposal = build_visualization_proposal(
        handle,
        title="Sales decision dashboard",
        roles={"date": "month", "branch": "branch", "sales": "revenue"},
        source_config={"type": "file", "file_name": "sales.xlsx"},
    )

    assert proposal["action"] == "propose_visualization"
    assert proposal["row_count"] == 12
    assert len([item for item in proposal["widgets"] if item["kind"] == "chart"]) >= 2
    assert {item["field"] for item in proposal["filters"]} == {"month", "branch"}
    assert "rows" not in proposal
    assert proposal["source_config"] == {
        "type": "file",
        "file_name": "sales.xlsx",
        "json_path": None,
        "column_mapping": {},
        "cleaning_recipe": {},
        "cleaning_profile": "standard",
    }


def test_chat_visualization_context_is_owner_scoped_and_bounded():
    client = MagicMock()
    reports = MagicMock()
    reports.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{
        "id": "report-1",
        "user_id": "user-1",
        "title": "Sales dashboard",
        "executive_summary": "Verified summary",
        "dataset_key": "sales.xlsx",
        "conversation_id": "conversation-1",
        "source_config": {
            "type": "file",
            "file_name": "sales.xlsx",
            "secret": "must-not-leak",
        },
        "dashboard_spec": {
            "filters": [{"field": "branch", "kind": "text"}],
            "widgets": [{
                "id": "ranking",
                "kind": "chart",
                "title": "Revenue by branch",
                "chart_type": "bar",
                "dimension": "branch",
                "measure": "revenue",
                "aggregation": "sum",
                "private": "hidden",
            }],
        },
    }]
    client.table.return_value = reports

    context = build_chat_visualization_context(
        "user-1",
        {"report_id": "report-1", "widget_id": "ranking", "filters": {"branch": "North"}},
        client=client,
    )

    assert context["report_id"] == "report-1"
    assert context["widget"]["title"] == "Revenue by branch"
    assert context["filters"] == {"branch": "North"}
    assert context["_source_identity"] == {
        "type": "file",
        "file_name": "sales.xlsx",
        "connection_id": None,
    }
    assert "source_config" not in context
    assert "private" not in context["widget"]


def test_chat_visualization_context_rejects_unknown_widget_or_filter():
    client = MagicMock()
    reports = MagicMock()
    reports.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{
        "id": "report-1",
        "dashboard_spec": {
            "filters": [{"field": "branch"}],
            "widgets": [{"id": "ranking", "kind": "chart"}],
        },
    }]
    client.table.return_value = reports

    with pytest.raises(VisualizationError, match="widget not found"):
        build_chat_visualization_context(
            "user-1",
            {"report_id": "report-1", "widget_id": "missing", "filters": {}},
            client=client,
        )
    with pytest.raises(VisualizationError, match="filter is not part"):
        build_chat_visualization_context(
            "user-1",
            {"report_id": "report-1", "filters": {"customer_secret": "x"}},
            client=client,
        )


def test_report_conversation_binding_is_owner_checked_and_one_time(monkeypatch):
    client = MagicMock()
    reports = MagicMock()
    conversations = MagicMock()
    reports.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{
        "id": "report-1",
        "user_id": "user-1",
        "conversation_id": None,
    }]
    conversations.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{
        "id": "conversation-1",
    }]
    reports.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{
        "id": "report-1",
        "conversation_id": "conversation-1",
    }]
    client.table.side_effect = lambda name: {
        "visualization_reports": reports,
        "conversations": conversations,
    }[name]
    monkeypatch.setattr(
        "app.services.visualizations.enforce_customer_storage_quota",
        MagicMock(),
    )

    updated = update_report(
        "user-1",
        "report-1",
        {"conversation_id": "conversation-1"},
        client=client,
    )

    assert updated["conversation_id"] == "conversation-1"
    assert reports.update.call_args.args[0]["conversation_id"] == "conversation-1"

    reports.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{
        "id": "report-1",
        "user_id": "user-1",
        "conversation_id": "conversation-other",
    }]
    with pytest.raises(VisualizationError, match="already linked"):
        update_report(
            "user-1",
            "report-1",
            {"conversation_id": "conversation-1"},
            client=client,
        )


def test_dashboard_aggregates_and_filters_the_full_dataset_server_side():
    frame = pd.DataFrame(
        {
            "branch": ["A"] * 6000 + ["B"] * 4000,
            "revenue": [2] * 6000 + [3] * 4000,
        }
    )
    handle = DatasetHandle.from_dataframe(frame)
    spec = {
        "filters": [{"field": "branch", "kind": "text"}],
        "kpis": [
            {"kind": "count", "field": None, "label": "Rows"},
            {"kind": "sum", "field": "revenue", "label": "Revenue"},
        ],
        "widgets": [
            {
                "id": "ranking",
                "kind": "chart",
                "chart_type": "bar",
                "title": "Revenue by branch",
                "dimension": "branch",
                "measure": "revenue",
                "aggregation": "sum",
                "limit": 10,
                "span": 6,
            }
        ],
    }

    full = _dashboard_data(handle, spec)
    filtered = _dashboard_data(handle, spec, filters={"branch": "B"})

    assert full["kpis"][0]["value"] == 10_000
    assert full["kpis"][1]["value"] == 24_000
    assert len(full["widgets"][0]["data"]) == 2
    assert filtered["kpis"][0]["value"] == 4_000
    assert filtered["kpis"][1]["value"] == 12_000
    assert filtered["filtered_row_count"] == 4_000
    assert filtered["widgets"][0]["data"] == [{"name": "B", "value": 12_000.0}]
    assert json.loads(json.dumps(full, allow_nan=False)) == full


def test_dashboard_text_filter_matches_schema_choice_despite_source_whitespace():
    handle = DatasetHandle.from_dataframe(
        pd.DataFrame({"branch": ["North ", "South"], "revenue": [10, 20]})
    )
    spec = {
        "filters": [{"field": "branch", "kind": "text"}],
        "kpis": [{"kind": "count", "field": None, "label": "Rows"}],
        "widgets": [{
            "id": "branches",
            "kind": "chart",
            "chart_type": "bar",
            "title": "Revenue by branch",
            "dimension": "branch",
            "measure": "revenue",
            "aggregation": "sum",
            "limit": 10,
            "span": 6,
        }],
    }

    filtered = _dashboard_data(handle, spec, filters={"branch": "North"})

    assert filtered["filtered_row_count"] == 1
    assert filtered["kpis"][0]["value"] == 1
    assert filtered["widgets"][0]["data"] == [{"name": "North ", "value": 10.0}]


def test_v4_public_share_removes_private_source_and_detail_evidence():
    dashboard = {
        "source": {"type": "file", "file_name": "private.xlsx"},
        "schema": [{"name": "branch", "kind": "text", "options": ["A", "B"]}],
        "widgets": [
            {"id": "chart", "kind": "chart", "data": [{"name": "A", "value": 10}]},
            {"id": "detail", "kind": "table", "data": [{"customer": "secret"}]},
        ],
        "spec": {
            "version": 4,
            "widgets": [
                {"id": "chart", "kind": "chart", "purpose": "ranking"},
                {"id": "detail", "kind": "table", "purpose": "detail"},
            ],
            "kpis": [],
            "sections": [
                {"id": "drivers", "purpose": "drivers", "layout": "balanced", "widget_ids": ["chart"]},
                {"id": "records", "purpose": "detail", "layout": "detail", "widget_ids": ["detail"]},
            ],
        },
        "story": {
            "evidence_ids": ["context:query", "widget:chart", "widget:detail"],
            "evidence": [
                {"id": "context:query", "kind": "query_context", "source": {"file_name": "private.xlsx"}},
                {"id": "widget:chart", "kind": "widget", "widget_id": "chart"},
                {"id": "widget:detail", "kind": "widget", "widget_id": "detail", "preview": [{"customer": "secret"}]},
            ],
            "chapters": [{"id": "records", "evidence_ids": ["widget:detail"]}],
        },
    }

    sanitized = _sanitize_shared_dashboard_payload(dashboard, allow_detail_rows=False)

    assert sanitized["source"] == {}
    assert "options" not in sanitized["schema"][0]
    assert [item["id"] for item in sanitized["widgets"]] == ["chart"]
    assert [item["id"] for item in sanitized["spec"]["widgets"]] == ["chart"]
    assert "widget:detail" not in sanitized["story"]["evidence_ids"]
    assert sanitized["story"]["chapters"][0]["evidence_ids"] == []
    assert sanitized["story"]["evidence"][0]["source"] == {}
    assert dashboard["source"]["file_name"] == "private.xlsx"


def test_dashboard_editor_spec_is_bounded_and_schema_validated():
    schema = [
        {"name": "branch", "kind": "text", "distinct": 2, "options": ["A", "B"]},
        {"name": "revenue", "kind": "number", "distinct": 10, "options": []},
    ]
    spec = _normalize_dashboard_spec(
        {
            "title": "Editable",
            "filters": [{"field": "secret"}, {"field": "branch"}],
            "kpis": [{"kind": "sum", "field": "revenue", "label": "Revenue"}],
            "widgets": [
                {
                    "id": "ranking",
                    "kind": "chart",
                    "chart_type": "bar",
                    "title": "Revenue by branch",
                    "dimension": "branch",
                    "measure": "revenue",
                    "aggregation": "sum",
                    "span": 8,
                    "cross_filter": True,
                    "color": "#2563EB",
                },
                {
                    "id": "unsafe",
                    "kind": "chart",
                    "chart_type": "scatter",
                    "dimension": "secret",
                    "aggregation": "count",
                },
            ],
        },
        schema,
        title="Fallback",
    )

    assert spec["version"] == 4
    assert spec["sections"]
    assert spec["story"]["mode"] == "evidence_grounded"
    assert spec["filters"] == [{"field": "branch", "kind": "text"}]
    assert [widget["id"] for widget in spec["widgets"]] == ["ranking"]
    assert spec["widgets"][0]["span"] == 8
    assert spec["widgets"][0]["cross_filter"] is True
    assert spec["widgets"][0]["color"] == "#2563eb"


def test_dashboard_editor_can_remove_every_widget_and_kpi():
    spec = _normalize_dashboard_spec(
        {"title": "Blank canvas", "filters": [], "kpis": [], "widgets": []},
        [{"name": "branch", "kind": "text", "distinct": 2, "options": []}],
        title="Fallback",
    )

    assert spec["kpis"] == []
    assert spec["widgets"] == []


def test_dashboard_semantic_guardrails_flag_misleading_choices():
    warnings = _dashboard_semantic_warnings(
        {
            "kpis": [{"format": "percent"}],
            "widgets": [
                {
                    "id": "bad-pie",
                    "kind": "chart",
                    "chart_type": "pie",
                    "dimension": "category",
                    "measure": "product_id",
                    "aggregation": "sum",
                    "limit": 12,
                },
                {
                    "id": "bad-line",
                    "kind": "chart",
                    "chart_type": "line",
                    "dimension": "category",
                    "aggregation": "count",
                },
            ],
        },
        [
            {"name": "category", "kind": "text", "distinct": 80},
            {"name": "product_id", "kind": "number", "distinct": 80},
        ],
    )

    assert {warning["code"] for warning in warnings} == {
        "pie_high_cardinality",
        "identifier_aggregation",
        "non_temporal_trend",
        "percent_scale_check",
    }


def test_dashboard_planner_json_extraction_accepts_fenced_object_only():
    assert _extract_json_object('```json\n{"spec": {"widgets": []}}\n```') == {
        "spec": {"widgets": []}
    }
    assert _extract_json_object("not json") is None


def test_dashboard_planner_invalid_output_falls_back_to_verified_spec():
    schema = [
        {"name": "branch", "kind": "text", "distinct": 2, "options": ["A", "B"]},
        {"name": "revenue", "kind": "number", "distinct": 10, "options": []},
    ]
    fallback = _build_dashboard_spec({"title": "Sales"}, schema)

    spec, rationale, reason = _resolve_planner_spec(
        None,
        fallback,
        schema,
        title="Sales",
    )

    assert spec == fallback
    assert rationale == {}
    assert reason == "invalid_ai_plan"


def test_dashboard_planner_valid_output_is_normalized_against_schema():
    schema = [
        {"name": "branch", "kind": "text", "distinct": 2, "options": ["A", "B"]},
        {"name": "revenue", "kind": "number", "distinct": 10, "options": []},
    ]
    fallback = _build_dashboard_spec({"title": "Sales"}, schema)
    proposed = {
        "spec": {
            "title": "Focused",
            "filters": [],
            "kpis": [{"kind": "sum", "field": "revenue", "label": "Revenue"}],
            "widgets": [{
                "id": "ranking",
                "kind": "chart",
                "chart_type": "bar",
                "title": "Revenue by branch",
                "dimension": "branch",
                "measure": "revenue",
                "aggregation": "sum",
            }],
        },
        "rationale": {"ranking": "Shows the strongest branches."},
    }

    spec, rationale, reason = _resolve_planner_spec(
        proposed,
        fallback,
        schema,
        title="Sales",
    )

    assert spec["title"] == "Focused"
    assert spec["widgets"][0]["dimension"] == "branch"
    assert rationale["ranking"].startswith("Shows")
    assert reason is None


def test_dashboard_aggregate_cache_is_owner_scoped_and_returns_copies():
    key = _dashboard_cache_key(
        "user-1",
        "report-1",
        {"type": "file", "file_name": "sales.csv"},
        {"version": 3, "widgets": []},
        {"branch": "A"},
        100,
        {"contract_hash": "contract-1"},
    )
    _dashboard_cache_set(key, {"kpis": [{"value": 10}], "widgets": []})
    first = _dashboard_cache_get(key)
    first["kpis"][0]["value"] = 999

    assert _dashboard_cache_get(key)["kpis"][0]["value"] == 10
    assert key != _dashboard_cache_key(
        "user-2",
        "report-1",
        {"type": "file", "file_name": "sales.csv"},
        {"version": 3, "widgets": []},
        {"branch": "A"},
        100,
        {"contract_hash": "contract-1"},
    )
    assert key != _dashboard_cache_key(
        "user-1",
        "report-1",
        {"type": "file", "file_name": "sales.csv"},
        {"version": 3, "widgets": []},
        {"branch": "A"},
        100,
        {"contract_hash": "contract-2"},
    )


def test_normalize_chart_uses_config_title_and_keeps_snapshot():
    chart = normalize_chart(
        {
            "chart_type": "bar",
            "config": {"title": "Revenue", "xAxis": "name"},
            "data": [{"name": "Jan", "revenue": 120}],
        }
    )

    assert chart["title"] == "Revenue"
    assert chart["chart_type"] == "bar"
    assert chart["data"][0]["revenue"] == 120


@pytest.mark.parametrize("chart_type", ["scatter", "", "table"])
def test_normalize_chart_rejects_unsupported_types(chart_type):
    with pytest.raises(VisualizationError, match="Unsupported chart type"):
        normalize_chart(
            {
                "chart_type": chart_type,
                "data": [{"name": "Jan", "value": 1}],
            }
        )


def test_normalize_chart_rejects_empty_or_oversized_data():
    with pytest.raises(VisualizationError, match="non-empty"):
        normalize_chart({"chart_type": "line", "data": []})
    with pytest.raises(VisualizationError, match="500 rows"):
        normalize_chart(
            {
                "chart_type": "line",
                "data": [{"name": str(index), "value": index} for index in range(501)],
            }
        )


def test_create_report_checks_conversation_owner_and_enforces_quota(monkeypatch):
    client = MagicMock()
    conversations = MagicMock()
    reports = MagicMock()
    conversations.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "conversation-1"}
    ]
    reports.insert.return_value.execute.return_value.data = [
        {
            "id": "report-1",
            "user_id": "user-1",
            "title": "Monthly review",
        }
    ]
    client.table.side_effect = lambda name: {
        "conversations": conversations,
        "visualization_reports": reports,
    }[name]
    quota = MagicMock()
    monkeypatch.setattr(
        "app.services.visualizations.enforce_customer_storage_quota",
        quota,
    )

    result = create_report(
        "user-1",
        title="Monthly review",
        conversation_id="conversation-1",
        dashboard_spec={
            "title": "Monthly review",
            "filters": [{"field": "branch", "kind": "text"}],
            "kpis": [{"kind": "count", "label": "Rows", "field": None}],
            "widgets": [
                {
                    "id": "ranking",
                    "kind": "chart",
                    "chart_type": "bar",
                    "dimension": "branch",
                    "measure": "revenue",
                }
            ],
        },
        source_config={"type": "file", "file_name": "sales.xlsx"},
        client=client,
    )

    assert result["id"] == "report-1"
    assert result["charts"] == []
    quota.assert_called_once()
    inserted = reports.insert.call_args.args[0]
    assert inserted["user_id"] == "user-1"
    assert inserted["conversation_id"] == "conversation-1"
    assert inserted["dashboard_spec"]["widgets"][0]["id"] == "ranking"
    assert inserted["source_config"]["file_name"] == "sales.xlsx"


def test_generate_dashboard_does_not_erase_spec_when_source_is_missing(monkeypatch):
    client = MagicMock()
    reports = MagicMock()
    charts = MagicMock()
    reports.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{
        "id": "report-1",
        "user_id": "user-1",
        "title": "Sales",
        "source_config": {},
        "dashboard_spec": {
            "filters": [{"field": "branch", "kind": "text"}],
            "widgets": [{"id": "ranking", "kind": "chart"}],
        },
    }]
    charts.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = []
    client.table.side_effect = lambda name: {
        "visualization_reports": reports,
        "visualization_charts": charts,
    }[name]
    monkeypatch.setattr(
        "app.services.visualizations._infer_source_config",
        lambda *_args, **_kwargs: {},
    )

    with pytest.raises(VisualizationError, match="saved layout was not changed"):
        generate_dashboard("user-1", "report-1", client=client)

    reports.update.assert_not_called()


def test_generate_dashboard_recovers_legacy_zero_row_report(monkeypatch):
    client = MagicMock()
    reports = MagicMock()
    reports.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{
        "id": "report-1",
        "user_id": "user-1",
        "title": "Sales",
        "conversation_id": "conversation-1",
        "source_config": {},
        "dashboard_spec": {"version": 3, "filters": [], "kpis": [], "widgets": []},
    }]
    client.table.return_value = reports
    monkeypatch.setattr(
        "app.services.visualizations._infer_source_config",
        lambda *_args, **_kwargs: {"type": "file", "file_name": "sales.xlsx"},
    )
    monkeypatch.setattr(
        "app.services.visualizations._load_dashboard_handle",
        lambda *_args, **_kwargs: DatasetHandle.from_dataframe(pd.DataFrame({
            "branch": ["A", "B"],
            "revenue": [10, 20],
        })),
    )
    monkeypatch.setattr(
        "app.services.visualizations._save_dashboard_revision",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.visualizations.enforce_customer_storage_quota",
        lambda *_args, **_kwargs: None,
    )

    dashboard = generate_dashboard("user-1", "report-1", client=client)

    assert dashboard["row_count"] == 2
    assert dashboard["spec"]["widgets"]
    assert dashboard["analysis_intent"]["primary"] == "overview"
    assert len(dashboard["dashboard_planning"]["composition_candidates"]) == 3
    assert dashboard["dashboard_planning"]["widget_candidates_evaluated"] >= 1
    schema_by_name = {item["name"]: item for item in dashboard["schema"]}
    assert schema_by_name["revenue"]["semantic_role"] == "sales"
    assert schema_by_name["revenue"]["semantic_type"] == "measure"
    persisted = reports.update.call_args.args[0]
    assert persisted["source_config"]["file_name"] == "sales.xlsx"
    assert persisted["dashboard_spec"]["widgets"]


def test_create_report_rejects_cross_user_conversation():
    client = MagicMock()
    conversations = MagicMock()
    conversations.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    client.table.return_value = conversations

    with pytest.raises(VisualizationError, match="does not belong"):
        create_report(
            "user-1",
            title="Private report",
            conversation_id="other-users-conversation",
            client=client,
        )


def test_list_reports_groups_only_owner_charts():
    client = MagicMock()
    reports_table = MagicMock()
    charts_table = MagicMock()
    reports_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "report-1", "user_id": "user-1", "title": "One"},
        {"id": "report-2", "user_id": "user-1", "title": "Two"},
    ]
    charts_table.select.return_value.eq.return_value.in_.return_value.order.return_value.order.return_value.execute.return_value.data = [
        {"id": "chart-1", "report_id": "report-2", "user_id": "user-1"}
    ]
    client.table.side_effect = lambda name: {
        "visualization_reports": reports_table,
        "visualization_charts": charts_table,
    }[name]

    result = list_reports("user-1", client=client)

    assert result[0]["charts"] == []
    assert result[1]["charts"][0]["id"] == "chart-1"
    charts_table.select.return_value.eq.assert_called_once_with("user_id", "user-1")


def test_shared_filter_request_does_not_consume_another_view(monkeypatch):
    client = MagicMock()
    shares = MagicMock()
    shares.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{
        "id": "share-1",
        "report_id": "report-1",
        "user_id": "user-1",
        "allow_detail_rows": False,
        "expires_at": "2099-01-01T00:00:00+00:00",
        "revoked_at": None,
        "max_views": 1,
        "access_count": 1,
        "last_accessed_at": "2026-01-01T00:00:00+00:00",
    }]
    client.table.return_value = shares
    monkeypatch.setattr(
        "app.services.visualizations._owned_report",
        lambda *_args, **_kwargs: {"id": "report-1", "title": "Shared"},
    )
    monkeypatch.setattr(
        "app.services.visualizations.generate_dashboard",
        lambda *_args, **_kwargs: {
            "report_id": "report-1",
            "spec": {"filters": [], "kpis": [], "widgets": []},
            "kpis": [],
            "widgets": [],
            "applied_filters": {"region": "north"},
        },
    )

    result = get_shared_dashboard(
        "00000000-0000-4000-8000-000000000001",
        filters={"region": "north"},
        count_view=False,
        client=client,
    )

    assert result["share"]["access_count"] == 1
    shares.update.assert_not_called()


def test_versioned_dashboard_cache_hit_skips_source_load(monkeypatch):
    handle = DatasetHandle.from_dataframe(
        pd.DataFrame({"region": ["north", "south"], "revenue": [10, 20]})
    )
    report = {
        "id": "report-cache-first",
        "title": "Revenue",
        "conversation_id": None,
        "source_config": {
            "type": "file",
            "file_name": "prepared.parquet",
            "dataset_version_id": "version-cache-first",
            "source_fingerprint": "fingerprint-cache-first",
            "cleaning_recipe": {"materialized_prepared": True},
        },
        "dashboard_spec": {
            "title": "Revenue",
            "filters": [{"field": "region", "kind": "text"}],
            "kpis": [{"kind": "sum", "label": "Revenue", "field": "revenue"}],
            "widgets": [],
        },
    }
    load = MagicMock(return_value=handle)
    monkeypatch.setattr(
        "app.services.visualizations._owned_report",
        lambda *_args, **_kwargs: report,
    )
    monkeypatch.setattr(
        "app.services.visualizations._load_dashboard_handle",
        load,
    )

    first = generate_dashboard(
        "user-cache-first",
        "report-cache-first",
        filters={"region": "north"},
        persist=False,
        client=MagicMock(),
    )
    second = generate_dashboard(
        "user-cache-first",
        "report-cache-first",
        filters={"region": "north"},
        persist=False,
        client=MagicMock(),
    )

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    load.assert_called_once()
