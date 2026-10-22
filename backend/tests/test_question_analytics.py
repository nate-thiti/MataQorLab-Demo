"""Tests for aggregate-only question analytics output."""
import asyncio
import pandas as pd

from app.services.question_analytics import (
    extract_sql_code,
    format_aggregate_result,
    run_question_aware_analytics,
)


def test_format_aggregate_scalar():
    df = pd.DataFrame({"total_sales": [1234567.89]})
    out = format_aggregate_result(df)
    assert "total_sales" in out
    assert "1234567" in out.replace(",", "")


def test_format_aggregate_groups_not_csv():
    df = pd.DataFrame(
        {
            "region": ["North", "South", "East"],
            "revenue": [100, 200, 150],
        }
    )
    out = format_aggregate_result(df)
    assert "Aggregate summary" in out
    assert "North" in out
    assert ".csv" not in out.lower()
    assert "region,revenue" not in out


def test_extract_sql_code_from_explanatory_response():
    text = """
    Here is the query:

    ```sql
    SELECT "region", SUM("sales") AS total_sales
    FROM df
    GROUP BY 1;
    ```
    """

    sql = extract_sql_code(text)

    assert sql.startswith('SELECT "region"')
    assert "```" not in sql
    assert not sql.endswith(";")


def test_extract_sql_code_allows_cte():
    text = """
    ```sql
    WITH sales_by_region AS (
      SELECT region, SUM(sales) AS total_sales FROM df GROUP BY region
    )
    SELECT * FROM sales_by_region LIMIT 10;
    ```
    """

    sql = extract_sql_code(text)

    assert sql.startswith("WITH sales_by_region")
    assert sql.endswith("LIMIT 10")


def test_extract_sql_code_drops_a_second_top_level_query():
    text = """
    ```sql
    SELECT region, SUM(sales) AS total_sales
    FROM df
    GROUP BY region
    -- Alternative for DuckDB:
    SELECT AVG(sales) FROM df
    ```
    """

    sql = extract_sql_code(text)

    assert "SUM(sales)" in sql
    assert "AVG(sales)" not in sql


def test_extract_sql_code_keeps_the_final_select_of_a_cte():
    text = """
    ```sql
    WITH grouped AS (
      SELECT region, SUM(sales) AS total_sales
      FROM df
      GROUP BY region
    )
    SELECT * FROM grouped
    ```
    """

    sql = extract_sql_code(text)

    assert "WITH grouped" in sql
    assert "SELECT * FROM grouped" in sql


def test_question_analytics_does_not_exceed_shared_llm_budget():
    async def scenario():
        calls = 0

        async def completion(**_kwargs):
            nonlocal calls
            calls += 1
            raise AssertionError("completion must not run without budget")

        completion.remaining_calls = lambda: 0
        result = await run_question_aware_analytics(
            pd.DataFrame({"label": ["A"], "value": [10]}),
            "Analyze this custom metric",
            "test-model",
            completion,
        )

        assert result["success"] is False
        assert result["attempts"] == 0
        assert "budget exhausted" in result["error"].lower()
        assert calls == 0

    asyncio.run(scenario())
