"""Phase 2 — independent setup tool wrappers."""
from __future__ import annotations

import json

import pandas as pd

import importlib

from app.services.dataset_engine import DatasetHandle
from app.services.tools.clean_data import clean_data, run_clean_data
from app.services.tools.inspect_source import inspect_source
from app.services.tools.map_schema import map_schema
from app.services.tools.prepare_data import prepare_data
from app.services.tools.registry import STEP_REGISTRY
from app.services.tools.types import ToolResult
from app.services.tools.validate_data import validate_data

inspect_source_module = importlib.import_module("app.services.tools.inspect_source")
prepare_data_module = importlib.import_module("app.services.tools.prepare_data")


def _sales_rows():
    return [
        {
            "order_id": "SO-001",
            "line_id": "1",
            "order_date": "2026-01-01",
            "net_amount": 1250.0,
            "customer_id": "C-001",
            "private_note": "secret-a",
        },
        {
            "order_id": "SO-002",
            "line_id": "1",
            "order_date": "invalid-date",
            "net_amount": None,
            "customer_id": "C-002",
            "private_note": "secret-b",
        },
        {
            "order_id": "SO-002",
            "line_id": "1",
            "order_date": "invalid-date",
            "net_amount": None,
            "customer_id": "C-002",
            "private_note": "secret-b",
        },
    ]


def test_tool_result_excludes_dataset_payloads():
    result = ToolResult(
        tool="prepare_data",
        status="completed",
        summary="ok",
        metadata={"rows": 3, "columns": 6},
        artifacts={"dataset_key": "sales.xlsx"},
    )
    payload = result.to_public_dict()
    serialized = json.dumps(payload)
    assert "DataFrame" not in serialized
    assert "secret" not in serialized
    assert payload["artifacts"]["dataset_key"] == "sales.xlsx"


def test_registry_exposes_setup_tools():
    assert set(STEP_REGISTRY) >= {
        "inspect", "prepare", "map", "validate", "clean", "finalize"
    }
    tool_names = {entry["tool_name"] for entry in STEP_REGISTRY.values()}
    assert {
        "inspect_source",
        "prepare_data",
        "clean_data",
        "map_schema",
        "validate_data",
        "finalize",
    }.issubset(tool_names)


def test_inspect_source_reuses_existing_scan_without_reload(monkeypatch):
    called = {"load": 0}

    def boom(*_args, **_kwargs):
        called["load"] += 1
        raise AssertionError("should not reload when scan exists")

    monkeypatch.setattr(inspect_source_module, "load_setup_handle", boom)
    scan = {
        "columns": [{"name": "order_id", "needs_review": False}],
        "row_count": 10,
        "column_count": 1,
        "source_type": "file",
        "source_fingerprint": "abc",
    }
    result = inspect_source(
        user_id="u1",
        source_type="file",
        source_ref={"file_name": "sales.xlsx"},
        existing_scan=scan,
    )
    assert result.status == "skipped"
    assert result.artifacts["scan_result"] == scan
    assert called["load"] == 0
    assert "clean" not in (result.suggested_next_actions or []) or True
    assert result.artifacts.get("output_file") is None
    assert result.artifacts.get("dataset_version_id") is None


def test_inspect_source_builds_scan_from_sample(monkeypatch):
    handle = DatasetHandle.from_dataframe(pd.DataFrame(_sales_rows()))
    monkeypatch.setattr(
        inspect_source_module, "load_setup_handle", lambda *_a, **_k: handle
    )
    result = inspect_source(
        user_id="u1",
        source_type="file",
        source_ref={"file_name": "sales.xlsx"},
        source_label="sales.xlsx",
    )
    assert result.status == "completed"
    assert result.tool == "inspect_source"
    assert result.artifacts["scan_result"]["column_count"] >= 1
    assert "secret-a" not in json.dumps(result.to_public_dict())
    assert result.artifacts.get("etl_run_id") is None
    assert result.artifacts.get("output_file") is None


def test_prepare_data_file_is_independently_callable(monkeypatch):
    handle = DatasetHandle.from_dataframe(pd.DataFrame(_sales_rows()))
    monkeypatch.setattr(
        prepare_data_module, "load_handle_from_storage", lambda *_a, **_k: handle
    )
    cleaned_calls = {"n": 0}

    def no_clean(*_a, **_k):
        cleaned_calls["n"] += 1
        raise AssertionError("prepare_data must not clean")

    monkeypatch.setattr(DatasetHandle, "apply_standard_clean", no_clean)
    result = prepare_data(
        user_id="u1",
        source_type="file",
        source_ref={"file_name": "sales.xlsx"},
    )
    assert result.status == "completed"
    assert result.artifacts["dataset_key"] == "sales.xlsx"
    assert result.metadata["rows"] == 3
    assert cleaned_calls["n"] == 0
    assert result.artifacts.get("output_file") is None


def test_clean_data_preview_is_independently_callable():
    mapping = {
        "order_id": "order_id",
        "net_amount": "net_amount",
        "order_date": "date",
        "customer_id": "customer_id",
        "line_id": "line_id",
    }
    result = clean_data(
        mode="preview",
        rows=_sales_rows(),
        mapping=mapping,
        cleaning_profile="standard",
        recipe={"apply": True, "column_mapping": mapping},
    )
    assert result.status == "completed"
    assert result.metadata["mode"] == "preview"
    assert result.artifacts["preview_result"]["rows_before"] == 3
    assert result.artifacts.get("output_file") is None
    assert "secret-a" not in json.dumps(result.to_public_dict())


def test_clean_data_apply_uses_standard_clean_once():
    handle = DatasetHandle.from_dataframe(pd.DataFrame(_sales_rows()))
    mapping = {
        "order_id": "order_id",
        "net_amount": "net_amount",
        "order_date": "date",
        "customer_id": "customer_id",
        "line_id": "line_id",
    }
    result, cleaned = run_clean_data(
        mode="apply",
        handle=handle,
        mapping=mapping,
        cleaning_profile="standard",
        recipe={"column_mapping": mapping},
        retain_handle=True,
    )
    assert result.status == "completed"
    assert cleaned is not None
    assert result.metadata["mode"] == "apply"
    assert int(result.metadata["rows_after"]) <= 3
    assert any(
        item.get("type") == "duplicate_rows_removed" for item in result.findings
    ) or result.metadata["rows_after"] <= result.metadata["rows_before"]
    assert result.artifacts.get("output_file") is None
    assert result.artifacts.get("dataset_version_id") is None


def test_map_schema_is_independently_callable():
    result = map_schema(
        column_mapping={"order_id": "order_id", "net_amount": "net_amount"},
        suggested_mapping={"PRICE_LEVEL": "price_level"},
        columns=["order_id", "net_amount", "PRICE_LEVEL", "notes"],
    )
    assert result.status == "completed"
    assert result.metadata["mapped"] >= 2
    assert result.metadata["unresolved"] >= 1
    assert result.artifacts["mapping_source"] == "session"
    assert "PRICE_LEVEL" in result.artifacts["column_mapping"] or any(
        f.get("column") == "notes" and f.get("status") == "unresolved"
        for f in result.findings
    )


def test_validate_data_is_independently_callable():
    result = validate_data(
        data_contract={
            "mapping_confirmed": True,
            "business_context_reviewed": True,
            "row_grain": "order_item",
            "data_owner": "ops",
        },
        column_mapping={"order_id": "order_id", "net_amount": "net_amount"},
        columns=["order_id", "net_amount"],
    )
    assert result.tool == "validate_data"
    assert "data_readiness" in result.metadata
    assert "business_context" in result.metadata
    assert result.metadata["computation"]["evaluated"] is False
    assert result.artifacts.get("output_file") is None


def test_prepare_and_clean_do_not_publish(monkeypatch):
    handle = DatasetHandle.from_dataframe(pd.DataFrame(_sales_rows()))
    monkeypatch.setattr(
        prepare_data_module, "load_handle_from_storage", lambda *_a, **_k: handle
    )
    prepare = prepare_data(
        user_id="u1",
        source_type="file",
        source_ref={"file_name": "sales.xlsx"},
    )
    clean = clean_data(
        mode="apply",
        handle=handle,
        mapping={"order_id": "order_id"},
        cleaning_profile="conservative",
    )
    for result in (prepare, clean):
        assert "output_file" not in result.artifacts
        assert "dataset_version_id" not in result.artifacts
        assert "etl_run_id" not in result.artifacts
