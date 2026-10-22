import json

from app.services.data_setup import build_scan_result, preview_setup_rows


def _sales_rows():
    return [
        {
            "order_id": "SO-001",
            "line_id": "1",
            "order_date": "2026-01-01",
            "net_amount": 1250.0,
            "customer_id": "C-001",
            "private_note": "never-persist-this-sample-value",
        },
        {
            "order_id": "SO-002",
            "line_id": "1",
            "order_date": "invalid-date",
            "net_amount": None,
            "customer_id": "C-002",
            "private_note": "another-secret-value",
        },
    ]


def test_quick_scan_builds_adaptive_contract_metadata_without_raw_values():
    scan = build_scan_result(
        _sales_rows(),
        source_type="file",
        source_label="sales.xlsx",
        row_count=2_400_000,
        row_count_exact=False,
    )

    assert scan["suggested_domain"] == "sales"
    assert scan["row_count"] == 2_400_000
    assert scan["row_count_exact"] is False
    assert scan["suggested_mapping"]["order_id"] == "order_id"
    assert scan["suggested_mapping"]["net_amount"] == "net_amount"
    assert scan["grain_options"][0]["value"] == "order_item"
    assert any(question["id"] == "revenue_basis" for question in scan["business_questions"])
    serialized = json.dumps(scan, ensure_ascii=False)
    assert "never-persist-this-sample-value" not in serialized
    assert "another-secret-value" not in serialized


def test_cleaning_preview_is_bounded_and_reports_required_resolutions():
    rows = _sales_rows() + [_sales_rows()[1]]
    scan = build_scan_result(rows, source_type="file", source_label="sales.xlsx")
    preview = preview_setup_rows(
        rows,
        mapping=scan["suggested_mapping"],
        cleaning_profile="standard",
        recipe={
            "apply": True,
            "column_mapping": scan["suggested_mapping"],
            "data_contract": {
                "row_grain": "order_item",
                "mapping_confirmed": True,
                "business_context_reviewed": True,
            },
        },
    )

    assert preview["rows_before"] == 3
    assert preview["rows_after"] <= 3
    assert any(item["column"] == "net_amount" for item in preview["missing_recommendations"])
    assert any(item["column"] == "order_date" for item in preview["invalid_date_issues"])
    assert "before" not in preview
    assert "after" not in preview
    assert "preview" not in preview["cleaning_report"]
    assert "never-persist-this-sample-value" not in json.dumps(preview, ensure_ascii=False)
    assert "contract_readiness" in preview
