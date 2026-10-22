import asyncio

import pandas as pd
import pytest

from app.services.agent_tool_registry import (
    AgentToolBudget,
    AgentToolContext,
    AgentToolDispatcher,
    ToolPermissionError,
)
from app.services.dataset_engine import DatasetHandle
from app.services.semantic_mapping_gate import (
    evaluate_semantic_mapping_gate,
    normalize_mapping,
)
from app.services.tools.validate_data import validate_data


def test_mapping_gate_requires_confirmed_analytical_mapping():
    unconfirmed = evaluate_semantic_mapping_gate(
        mapping={"amount": "sales"},
        data_contract={"mapping_confirmed": False},
        columns=["amount"],
    )
    confirmed = evaluate_semantic_mapping_gate(
        mapping={"amount": "sales"},
        data_contract={"mapping_confirmed": True},
        columns=["amount"],
    )

    assert unconfirmed["ready"] is False
    assert "mapping_confirmation_required" in {item["code"] for item in unconfirmed["issues"]}
    assert confirmed["ready"] is True


def test_mapping_gate_uses_dataset_specific_critical_roles():
    inventory = evaluate_semantic_mapping_gate(
        mapping={"SnapshotDate": "date"},
        data_contract={"mapping_confirmed": True},
        columns=["SnapshotDate", "StockOnHand", "SKU"],
        suggested_mapping={
            "SnapshotDate": "date",
            "StockOnHand": "stock_level",
            "SKU": "product",
        },
    )

    assert inventory["ready"] is False
    assert inventory["missing_required_roles"] == ["stock_level"]
    assert "sales" not in inventory["required_roles"]


def test_mapping_aliases_compare_as_canonical_roles():
    assert normalize_mapping({"net_sales": "revenue", "invoice": "invoice"}) == {
        "net_sales": "sales",
        "invoice": "invoice_id",
    }


def test_validate_data_waits_for_mapping_confirmation():
    result = validate_data(
        data_contract={
            "mapping_confirmed": False,
            "business_context_reviewed": True,
            "row_grain": "order",
            "data_owner": "ops",
            "business_purpose": "reporting",
            "metric_definition": "sum sales",
            "period_status": "complete",
        },
        column_mapping={"amount": "sales"},
        columns=["amount"],
    )

    assert result.status == "awaiting_user"
    assert result.metadata["semantic_mapping_ready"] is False


def test_agent_tools_block_analysis_but_allow_inspection_before_mapping():
    handle = DatasetHandle.from_dataframe(pd.DataFrame({"amount": [10, 20]}))
    context = AgentToolContext(
        user_id="user-1",
        handle=handle,
        column_mapping={"amount": "sales"},
        data_contract={"mapping_confirmed": False},
    )

    async def scenario():
        dispatcher = AgentToolDispatcher()
        with pytest.raises(ToolPermissionError, match="SEMANTIC_MAPPING_REQUIRED"):
            await dispatcher.execute(
                {"tool_id": "compute_metrics", "arguments": {"column": "amount"}},
                context=context,
                budget=AgentToolBudget(max_calls=3, max_cost_units=5),
            )
        inspected = await dispatcher.execute(
            {"tool_id": "inspect_dataset", "arguments": {"sample_rows": 1}},
            context=context,
            budget=AgentToolBudget(max_calls=3, max_cost_units=5),
        )
        assert inspected.record.status == "completed"
        assert inspected.output["row_count"] == 2

    asyncio.run(scenario())
