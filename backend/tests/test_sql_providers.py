"""Tests for multi-provider SQL connection URL building."""
import pytest

from app.services.sql_execution import (
    SUPPORTED_DB_PROVIDERS,
    build_db_url,
    is_supported_db_provider,
)


def test_supported_providers_include_new_vendors():
    assert "mariadb" in SUPPORTED_DB_PROVIDERS
    assert "snowflake" in SUPPORTED_DB_PROVIDERS
    assert "clickhouse" in SUPPORTED_DB_PROVIDERS
    assert is_supported_db_provider("oracle")


def test_build_db_url_postgres():
    url = build_db_url("postgres", "user", "p@ss", "localhost", 5432, "app")
    assert url.startswith("postgresql+psycopg2://user:p%40ss@localhost:5432/app")


def test_build_db_url_mariadb_uses_mysql_driver():
    url = build_db_url("mariadb", "root", "secret", "db.local", 3306, "sales")
    assert url.startswith("mysql+pymysql://")


def test_build_db_url_snowflake():
    url = build_db_url(
        "snowflake",
        "USER",
        "TOKEN",
        "xy123.us-east-1.snowflakecomputing.com",
        443,
        "ANALYTICS",
    )
    assert "snowflake://USER:TOKEN@" in url
    assert url.endswith("/ANALYTICS")


def test_build_db_url_rejects_unknown():
    with pytest.raises(ValueError):
        build_db_url("sqlite", "u", "p", "h", 1, "d")
