import asyncio

import pandas as pd

from app.services.answer_verifier import (
    needs_numeric_correction,
    verify_answer,
)
from app.services.dataset_engine import DatasetHandle
from app.services.narration_corrector import retry_narration_for_numeric_mismatch
from app.services.question_decomposer import decompose_analysis_question
from app.services.sql_templates import match_sql_template, validate_llm_sql
from app.services.structured_findings import (
    build_analysis_eligibility,
    build_response_outline,
    build_structured_findings,
)


def _sales_handle() -> DatasetHandle:
    dates = pd.date_range("2024-01-01", periods=30, freq="MS")
    rows = []
    for index, date in enumerate(dates):
        rows.extend(
            [
                {
                    "order_date": date,
                    "country": "US",
                    "customer_id": f"c{index % 8}",
                    "revenue": 100 + index,
                },
                {
                    "order_date": date,
                    "country": "DE",
                    "customer_id": f"c{(index + 1) % 8}",
                    "revenue": 40 + index,
                },
            ]
        )
    return DatasetHandle.from_dataframe(pd.DataFrame(rows))


def test_structured_findings_have_provenance_and_deep_statistics():
    handle = _sales_handle()
    analytics = {
        "detected_roles": {
            "date": "order_date",
            "sales": "revenue",
            "country": "country",
        }
    }

    findings = build_structured_findings(
        handle, analytics, compute_depth="deep", max_findings=24
    )

    assert findings
    assert all(item["id"].startswith("f_") for item in findings)
    assert all(item["provenance"]["result_hash"] for item in findings)
    assert any(item["type"] == "pareto" for item in findings)
    assert any(item["type"] == "seasonality" for item in findings)
    assert any(item["type"] == "cohort_retention" for item in findings)


def test_eligibility_gates_explain_missing_requirements():
    handle = DatasetHandle.from_dataframe(pd.DataFrame({"label": ["a", "b"]}))

    gates = build_analysis_eligibility(handle)

    assert gates["seasonality"]["eligible"] is False
    assert "requires" in gates["seasonality"]
    assert gates["benford"]["eligible"] is False


def test_sql_template_runs_before_llm_for_unambiguous_total():
    handle = _sales_handle()

    template = match_sql_template(handle, "What is total revenue?")

    assert template
    assert template["template_id"] == "total_metric"
    result = handle.execute_select(template["sql"])
    assert result.iloc[0, 0] > 0


def test_visualization_request_uses_deterministic_overview_before_llm():
    handle = _sales_handle()

    template = match_sql_template(
        handle,
        "วิเคราะห์ข้อมูลที่เลือกและสร้างรายงาน Visualization "
        "แบบกระชับ พร้อมกราฟที่ช่วยตัดสินใจมากที่สุด",
    )

    assert template
    assert template["template_id"] == "visualization_overview"
    result = handle.execute_select(template["sql"])
    assert set(result.columns) == {"country", "total_revenue"}
    assert result["total_revenue"].sum() > 0


def test_dataset_verifier_uses_rounding_tolerance_and_flags_new_numbers():
    findings = [
        {
            "value": 1234.567,
            "metric": "total_revenue",
            "unit": "USD",
        }
    ]

    grounded = verify_answer(
        "Revenue is 1,235.",
        has_dataset_metrics=True,
        structured_findings=findings,
    )
    invented = verify_answer(
        "Revenue is 9,999.",
        has_dataset_metrics=True,
        structured_findings=findings,
    )

    assert grounded["status"] == "grounded"
    assert grounded["matched_dataset_numeric_claim_count"] == 1
    assert invented["status"] == "needs_review"


def test_server_outline_and_question_plan_separate_compute_from_narration():
    outline = build_response_outline(
        [
            {
                "type": "aggregate",
                "metric": "total_revenue",
                "value": 100,
                "unit": "USD",
                "evidence": "Computed on all rows.",
            }
        ],
        compute_depth="deep",
    )
    plan = decompose_analysis_question(
        "Why did growth change and which country contributed?",
        roles={"date": "order_date", "sales": "revenue"},
        compute_depth="deep",
    )

    assert "Verified analysis" in outline
    assert "Interpretation" in outline
    assert any(step["id"] == "drivers" for step in plan["steps"])
    assert plan["narration_contract"] == [
        "evidence",
        "interpretation",
        "suggested_action",
    ]


def test_verifier_ignores_thai_structural_numbers():
    findings = [{"value": 1234.567, "metric": "total_revenue", "unit": "USD"}]

    result = verify_answer(
        "ข้อเสนอ 3 ข้อ: 1) ตรวจสอบ margin 2) ดู top 10 สาขา 3) ติดตามแนวโน้ม\n"
        "ยอดรวม 1,235",
        has_dataset_metrics=True,
        structured_findings=findings,
    )

    assert result["status"] == "grounded"
    assert result["matched_dataset_numeric_claim_count"] == 1
    assert "3" not in (result.get("unmatched_dataset_numeric_claims") or [])


def test_needs_numeric_correction_only_for_dataset_mismatch():
    verification = verify_answer(
        "Revenue is 9,999.",
        has_dataset_metrics=True,
        structured_findings=[{"value": 100, "metric": "revenue", "unit": "USD"}],
    )
    assert needs_numeric_correction(verification) is True
    assert verification["numeric_correction_required"] is True


def test_validate_llm_sql_rejects_raw_select_star():
    handle = _sales_handle()
    ok, errors = validate_llm_sql("SELECT * FROM df", "What is total revenue?", handle)
    assert ok is False
    assert any("GROUP BY" in err or "aggregate" in err.lower() for err in errors)


def test_narration_corrector_retries_on_numeric_mismatch():
    findings = [{"id": "f1", "value": 100, "metric": "revenue", "unit": "USD", "evidence": "sum"}]
    verification = verify_answer(
        "Revenue reached 9,999.",
        has_dataset_metrics=True,
        structured_findings=findings,
    )

    class FakeResponse:
        class Choice:
            class Message:
                content = "Revenue reached 100."

            message = Message()

        choices = [Choice()]

    async def fake_completion(**kwargs):
        return FakeResponse()

    corrected, meta = asyncio.run(
        retry_narration_for_numeric_mismatch(
            "Revenue reached 9,999.",
            structured_findings=findings,
            verification=verification,
            model="test-model",
            chat_completion_fn=fake_completion,
        )
    )

    assert meta["applied"] is True
    assert "100" in corrected
