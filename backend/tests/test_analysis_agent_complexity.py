"""Open-ended analysis asks must enter the multi-tool agent."""
from __future__ import annotations

from app.services.analysis_agent import (
    is_complex_question,
    is_open_ended_analysis_request,
)


def test_thai_analyze_please_is_complex():
    assert is_complex_question("วิเคราะห์ข้อมูลให้หน่อย") is True
    assert is_open_ended_analysis_request("วิเคราะห์ข้อมูลให้หน่อย") is True


def test_english_analyze_dataset_is_complex():
    assert is_complex_question("Analyze this dataset please") is True
    assert is_open_ended_analysis_request("Analyze this dataset please") is True


def test_specific_compare_stays_specific():
    q = "เปรียบเทียบยอดขายเดือนนี้กับเดือนที่แล้วทำไมถึงต่าง"
    assert is_complex_question(q) is True
    assert is_open_ended_analysis_request(q) is False


def test_tiny_greeting_not_complex():
    assert is_complex_question("สวัสดี") is False
    assert is_open_ended_analysis_request("สวัสดี") is False
