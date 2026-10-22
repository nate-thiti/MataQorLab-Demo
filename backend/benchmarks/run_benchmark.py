#!/usr/bin/env python3
"""Reproducible compute-first benchmark with optional OpenRouter model baselines."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.analysis_audit import build_analysis_audit
from app.services.analytical_extensions import assess_join_cardinality, infer_grain_and_join_risks
from app.services.answer_verifier import verify_answer
from app.services.dataset_engine import DatasetHandle
from app.services.domain_analytics import infer_semantic_roles
from app.services.question_decomposer import decompose_analysis_question
from app.services.structured_findings import (
    build_analysis_eligibility,
    build_column_intelligence,
    build_structured_findings,
)


def global_sales() -> pd.DataFrame:
    countries = ["US", "DE", "JP", "BR"]
    rows = []
    for month, date in enumerate(pd.date_range("2024-01-01", periods=24, freq="MS")):
        for index, country in enumerate(countries):
            revenue = 1000 + month * 50 + index * 100
            rows.append(
                {
                    "order_date": date,
                    "order_id": f"o-{month}-{index}",
                    "customer_id": f"c-{(month + index) % 20}",
                    "country": country,
                    "channel": "direct" if index % 2 == 0 else "partner",
                    "revenue": revenue,
                    "cost": revenue * 0.6,
                    "quantity": 100 + month + index,
                }
            )
    return pd.DataFrame(rows)


def marketing() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=12, freq="MS"),
            "channel": ["search", "social", "email"] * 4,
            "impressions": [10_000] * 12,
            "clicks": [500] * 12,
            "ad_spend": [1_000 + index * 20 for index in range(12)],
        }
    )


def manufacturing() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=12, freq="MS"),
            "plant": ["A", "B"] * 6,
            "output": [10_000] * 12,
            "defects": [200] * 12,
        }
    )


def missing_data() -> pd.DataFrame:
    return pd.DataFrame({"country": ["US", None, "DE", None], "revenue": [100, 200, None, 400]})


def order_lines() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"order_id": f"o-{order}", "line_id": line, "revenue": 10 + line}
            for order in range(10)
            for line in range(3)
        ]
    )


FIXTURES = {
    "global_sales": global_sales,
    "marketing": marketing,
    "manufacturing": manufacturing,
    "missing_data": missing_data,
    "order_lines": order_lines,
}


@dataclass
class Score:
    case_id: str
    passed: bool
    score: float
    detail: str


def _roles(frame: pd.DataFrame) -> Dict[str, str]:
    return infer_semantic_roles(frame, {})


def _find_metric(findings: Iterable[Dict[str, Any]], key: str) -> Dict[str, Any] | None:
    return next((item for item in findings if item.get("metric") == key), None)


def run_platform_case(case: Dict[str, Any]) -> Score:
    if case["fixture"] == "join_pair":
        left = pd.DataFrame({"key": [1, 1, 2], "left_value": [10, 20, 30]})
        right = pd.DataFrame({"key": [1, 1, 3], "right_value": [5, 6, 7]})
        result = assess_join_cardinality(left, right, "key")
        passed = result["cardinality"] == case["expected_join"] and not result["safe"]
        return Score(case["id"], passed, 1.0 if passed else 0.0, json.dumps(result))

    frame = FIXTURES[case["fixture"]]()
    roles = _roles(frame)
    handle = DatasetHandle.from_dataframe(frame)
    analytics = {"detected_roles": roles}
    depth = "deep" if case["mode"] == "deep" else "base"
    findings = build_structured_findings(
        handle,
        analytics,
        compute_depth=depth,
        max_findings=32,
        question=case["question"],
    )
    eligibility = build_analysis_eligibility(handle, analytics)
    columns = build_column_intelligence(handle, analytics)
    grain = infer_grain_and_join_risks(handle, roles)
    plan = decompose_analysis_question(case["question"], roles=roles, compute_depth=depth)
    audit = build_analysis_audit(
        findings=findings,
        question_plan=plan,
        eligibility=eligibility,
        column_intelligence=columns,
        grain_intelligence=grain,
        compute_depth=depth,
    )

    if expected := case.get("expected_metric"):
        finding = _find_metric(findings, expected["key"])
        if not finding:
            return Score(case["id"], False, 0.0, f"missing metric {expected['key']}")
        error = abs(float(finding["value"]) - float(expected["value"]))
        passed = error <= float(expected.get("tolerance", 0))
        return Score(case["id"], passed, 1.0 if passed else 0.0, f"value={finding['value']} error={error}")
    if expected_type := case.get("expected_type"):
        passed = any(item.get("type") == expected_type for item in findings)
        return Score(case["id"], passed, 1.0 if passed else 0.0, f"types={sorted({f['type'] for f in findings})}")
    if expected_grain := case.get("expected_grain"):
        passed = grain["grain"] == expected_grain
        return Score(case["id"], passed, 1.0 if passed else 0.0, json.dumps(grain))
    if fields := case.get("expected_audit_fields"):
        missing = [field for field in fields if field not in audit]
        passed = not missing and all(
            finding.get("provenance", {}).get("result_hash") for finding in findings
        )
        return Score(case["id"], passed, 1.0 if passed else 0.0, f"missing={missing}")
    if case.get("expected_verification"):
        result = verify_answer(
            "Revenue is 999,999.",
            has_dataset_metrics=True,
            structured_findings=findings,
        )
        passed = result["status"] == case["expected_verification"]
        return Score(case["id"], passed, 1.0 if passed else 0.0, json.dumps(result))
    return Score(case["id"], False, 0.0, "case has no scoring contract")


def extract_numbers(text: str) -> List[float]:
    return [
        float(value.replace(",", ""))
        for value in re.findall(r"(?<![\w])-?\d[\d,]*(?:\.\d+)?", text or "")
    ]


def score_external_response(case: Dict[str, Any], text: str) -> float:
    expected = case.get("expected_metric")
    if not expected:
        return 0.5 if text.strip() else 0.0
    tolerance = max(float(expected.get("tolerance", 0)), abs(float(expected["value"])) * 0.005)
    return 1.0 if any(abs(number - float(expected["value"])) <= tolerance for number in extract_numbers(text)) else 0.0


def run_live_models(cases: List[Dict[str, Any]], models: List[str]) -> Dict[str, Any]:
    from openai import OpenAI

    key = os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY")
    if not key:
        raise RuntimeError("Set OPENROUTER_API_KEY or LLM_API_KEY for --live.")
    client = OpenAI(base_url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"), api_key=key)
    scoreboard: Dict[str, Any] = {}
    for model in models:
        results = []
        for case in cases:
            if case["fixture"] == "join_pair":
                continue
            frame = FIXTURES[case["fixture"]]()
            csv = frame.head(250).to_csv(index=False)
            prompt = (
                "Answer the analytical question from the CSV. Show the numeric result and concise reasoning. "
                "Do not use tools or external data.\n\n"
                f"Question: {case['question']}\n\nCSV:\n{csv}"
            )
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=500,
            )
            text = response.choices[0].message.content or ""
            results.append({"case_id": case["id"], "score": score_external_response(case, text), "response": text})
        scoreboard[model] = {
            "average_score": sum(item["score"] for item in results) / max(1, len(results)),
            "cases": results,
        }
    return scoreboard


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(Path(__file__).parent / "cases/global_analysis.json"))
    parser.add_argument("--output", default=str(Path(__file__).parent / "results/latest.json"))
    parser.add_argument("--live", action="store_true", help="Call external models through OpenRouter (costs tokens).")
    parser.add_argument(
        "--models",
        default="openai/gpt-5,google/gemini-2.5-pro,anthropic/claude-sonnet-4",
        help="Comma-separated OpenRouter model IDs used only with --live.",
    )
    args = parser.parse_args()
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    platform_scores = [run_platform_case(case) for case in cases]
    result: Dict[str, Any] = {
        "platform": {
            "passed": sum(score.passed for score in platform_scores),
            "total": len(platform_scores),
            "average_score": sum(score.score for score in platform_scores) / max(1, len(platform_scores)),
            "cases": [score.__dict__ for score in platform_scores],
        }
    }
    if args.live:
        result["external_models"] = run_live_models(
            cases,
            [model.strip() for model in args.models.split(",") if model.strip()],
        )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value.get("average_score") for key, value in result.items()}, indent=2))
    print(f"Detailed results: {output}")
    return 0 if result["platform"]["passed"] == result["platform"]["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
