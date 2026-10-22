import pandas as pd
import pytest

from app.services.dax_engine import DaxError, compile_dax_expression, parse_dax_expression, validate_dax_expression
from app.services.dataset_engine import DatasetHandle


def _measure(expression: str, frame: pd.DataFrame):
    compiled = compile_dax_expression(parse_dax_expression(expression), columns=frame.columns)
    return DatasetHandle.from_dataframe(frame).execute_select(
        f'SELECT {compiled} AS "value" FROM df', max_rows=2
    ).iloc[0, 0]


def test_measure_aggregation_and_divide_blank_semantics():
    frame = pd.DataFrame({"sales": [10, 20, None], "cost": [4, 6, 0]})
    assert _measure("SUM([sales])", frame) == 30
    assert _measure("DIVIDE(SUM([sales]), SUM([cost]), 0)", frame) == 3
    assert pd.isna(_measure("DIVIDE(SUM([sales]), 0)", frame))


def test_typed_ast_dependencies_and_hash_are_stable():
    first = validate_dax_expression("IF(SUM([sales]) > 0, SUM([sales]), 0)", columns=["sales"])
    second = validate_dax_expression("IF(SUM([sales]) > 0, SUM([sales]), 0)", columns=["sales"])
    assert first["executable"] is True
    assert first["dependencies"] == ["sales"]
    assert first["formula_hash"] == second["formula_hash"]
    assert first["normalized_ast"]["kind"] == "function"


def test_unknown_columns_and_functions_fail_closed():
    with pytest.raises(DaxError, match="DAX_UNSUPPORTED_FUNCTION"):
        parse_dax_expression("EVALUATE([sales])")
    result = validate_dax_expression("SUM([secret])", columns=["sales"])
    assert result["executable"] is False
    assert result["execution_error"] == "DAX_UNKNOWN_COLUMN:secret"


def test_context_functions_are_parsed_but_require_query_context():
    result = validate_dax_expression("TOTALYTD(SUM([sales]), [date])", columns=["sales", "date"])
    assert result["valid"] is True
    assert result["executable"] is False
    assert result["execution_error"] == "DAX_QUERY_CONTEXT_REQUIRED:TOTALYTD"


def test_calculated_column_rejects_aggregate_and_accepts_row_expression():
    rejected = validate_dax_expression("SUM([sales])", columns=["sales"], mode="calculated_column")
    accepted = validate_dax_expression("DIVIDE([sales], [quantity], 0)", columns=["sales", "quantity"], mode="calculated_column")
    assert rejected["executable"] is False
    assert accepted["executable"] is True
