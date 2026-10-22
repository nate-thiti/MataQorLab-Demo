import pandas as pd
import pytest

from app.services.chart_builder import (
    ChartBuilderError,
    add_chart,
    bind_chart_field,
    inspect_chart,
    list_chart_fields,
    schema_from_handle,
)
from app.services.dataset_engine import as_handle


SCHEMA = [
    {"name": "branch", "kind": "text"},
    {"name": "order_date", "kind": "date"},
    {"name": "revenue", "kind": "number"},
]


def test_list_chart_fields_splits_axis_and_values():
    fields = list_chart_fields(SCHEMA)
    assert [item["name"] for item in fields["dimensions"]] == ["branch", "order_date"]
    assert [item["name"] for item in fields["measures"]] == ["revenue"]
    assert fields["chart_types"] == ["bar", "line", "area", "pie", "pareto"]


def test_bind_axis_and_values_builds_inspectable_formula():
    widget = add_chart(SCHEMA, chart_type="bar")
    widget = bind_chart_field(widget, "axis", "branch", SCHEMA)
    widget = bind_chart_field(widget, "values", "revenue", SCHEMA, aggregation="sum")
    inspected = inspect_chart(widget, SCHEMA, point_count=3)

    assert widget["dimension"] == "branch"
    assert widget["measure"] == "revenue"
    assert inspected["formula"] == "SUM(revenue) GROUP BY branch"
    assert inspected["wells"]["axis"]["field"] == "branch"
    assert inspected["wells"]["values"]["field"] == "revenue"
    assert inspected["engine"] == "duckdb"
    assert inspected["source_columns"] == ["branch", "revenue"]
    assert inspected["wells"]["x"]["field"] == "branch"
    assert inspected["wells"]["y"]["field"] == "revenue"


def test_xy_aliases_do_not_overwrite_chart_title():
    widget = add_chart(SCHEMA, chart_type="bar", title="Sales mix")
    widget = bind_chart_field(widget, "x", "branch", SCHEMA)
    widget = bind_chart_field(widget, "y", "revenue", SCHEMA, aggregation="sum")
    assert widget["title"] == "Sales mix"
    assert widget["dimension"] == "branch"
    assert widget["measure"] == "revenue"


def test_bind_rejects_measure_on_axis():
    widget = add_chart(SCHEMA)
    with pytest.raises(ChartBuilderError, match="AXIS_NEEDS_DIMENSION"):
        bind_chart_field(widget, "axis", "revenue", SCHEMA)


def test_count_well_clears_measure():
    widget = add_chart(SCHEMA)
    widget = bind_chart_field(widget, "values", "*", SCHEMA)
    assert widget["aggregation"] == "count"
    assert widget["measure"] is None
    assert inspect_chart(widget, SCHEMA)["formula"].startswith("COUNT(*)")


def test_schema_from_handle_uses_dataset_columns():
    handle = as_handle(pd.DataFrame({
        "branch": ["A", "B"],
        "revenue": [10, 20],
    }))
    schema = schema_from_handle(handle)
    by_name = {item["name"]: item["kind"] for item in schema}
    assert by_name["branch"] == "text"
    assert by_name["revenue"] == "number"
