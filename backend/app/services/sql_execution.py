"""Safe, timed SELECT-only SQL execution for external database connections."""
import os
import re
import tempfile
from typing import List, Optional, Tuple
from urllib.parse import quote_plus

import duckdb
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.services.dataset_engine import TABLE_NAME, DatasetHandle
from app.services.network_security import validate_outbound_host

TABLE_NAME_RE = re.compile(r"^[a-zA-Z0-9_]+(\.[a-zA-Z0-9_]+)?$")

FORBIDDEN_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter", "truncate", "create", "grant", "revoke",
]

SUPPORTED_DB_PROVIDERS = frozenset({
    "postgres",
    "mysql",
    "mariadb",
    "mssql",
    "oracle",
    "db2",
    "snowflake",
    "bigquery",
    "redshift",
    "databricks",
    "clickhouse",
})

MYSQL_FAMILY = frozenset({"mysql", "mariadb"})
POSTGRES_FAMILY = frozenset({"postgres", "redshift"})


def _quote(value: str) -> str:
    return quote_plus(value or "")


def is_supported_db_provider(provider: str) -> bool:
    return (provider or "").lower() in SUPPORTED_DB_PROVIDERS


def validate_select_sql(sql_query: str) -> Tuple[bool, str]:
    lower_sql = (sql_query or "").strip().lower()
    if not lower_sql.startswith("select"):
        return False, "Only SELECT queries are permitted"
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", lower_sql):
            return False, f"Forbidden keyword: {kw}"
    return True, ""


def build_db_url(provider: str, username: str, password: str, host: str, port: int, db_name: str) -> str:
    provider = (provider or "").lower()
    if provider not in SUPPORTED_DB_PROVIDERS:
        raise ValueError(f"Unsupported database provider: {provider}")

    user = _quote(username)
    pwd = _quote(password)
    host = (host or "").strip()
    db = (db_name or "").strip()
    port = int(port)

    if provider in POSTGRES_FAMILY:
        return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
    if provider in MYSQL_FAMILY:
        return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}"
    if provider == "mssql":
        driver = quote_plus("ODBC Driver 18 for SQL Server")
        return f"mssql+pyodbc://{user}:{pwd}@{host}:{port}/{db}?driver={driver}"
    if provider == "oracle":
        return f"oracle+oracledb://{user}:{pwd}@{host}:{port}/?service_name={quote_plus(db)}"
    if provider == "db2":
        return f"db2+ibm_db://{user}:{pwd}@{host}:{port}/{db}"
    if provider == "snowflake":
        account_host = host.replace("https://", "").replace("http://", "").strip("/")
        return f"snowflake://{user}:{pwd}@{account_host}/{db}"
    if provider == "bigquery":
        return f"bigquery://{host}/{db}?credentials_path=&user_supplied_client=false"
    if provider == "databricks":
        workspace = host.replace("https://", "").replace("http://", "").strip("/")
        return (
            f"databricks+connector://token:{pwd}@{workspace}"
            f"?http_path=/sql/1.0/endpoints/{quote_plus(db)}&catalog=main&schema=default"
        )
    if provider == "clickhouse":
        secure = "true" if port == 8443 else "false"
        return f"clickhouse+http://{user}:{pwd}@{host}:{port}/{db}?secure={secure}"
    raise ValueError(f"Unsupported database provider: {provider}")


def create_db_engine(db_url: str, provider: str):
    parsed = make_url(db_url)
    if parsed.host:
        validate_outbound_host(parsed.host, int(parsed.port or 443))
    timeout = int(settings.SQL_QUERY_TIMEOUT_SECONDS)
    provider = (provider or "").lower()
    connect_args: dict = {"connect_timeout": 10}
    if provider in POSTGRES_FAMILY:
        connect_args["options"] = f"-c statement_timeout={timeout * 1000}"
    elif provider in MYSQL_FAMILY:
        connect_args["read_timeout"] = timeout
        connect_args["write_timeout"] = timeout
    return create_engine(db_url, connect_args=connect_args)


def validate_table_name(table_name: str) -> Tuple[bool, str]:
    name = (table_name or "").strip()
    if not name:
        return False, "Table name is required"
    if not TABLE_NAME_RE.match(name):
        return False, "Invalid table name (use letters, numbers, underscore, optional schema.table)"
    return True, ""


def build_select_all_query(table_name: str, limit: Optional[int] = None) -> str:
    from app.core.config import settings

    cap = limit if limit is not None else int(settings.SQL_SYNC_ROW_LIMIT)
    ok, err = validate_table_name(table_name)
    if not ok:
        raise ValueError(err)
    return f"SELECT * FROM {table_name.strip()} LIMIT {int(cap)}"


def list_db_tables(engine, provider: str) -> List[str]:
    """Return sorted table names; Postgres includes schema.table when not public."""
    inspector = inspect(engine)
    provider = (provider or "").lower()
    tables: List[str] = []
    if provider in POSTGRES_FAMILY:
        for schema in inspector.get_schema_names():
            if schema in ("information_schema", "pg_catalog") or schema.startswith("pg_"):
                continue
            for table in inspector.get_table_names(schema=schema):
                if schema == "public":
                    tables.append(table)
                else:
                    tables.append(f"{schema}.{table}")
    else:
        tables = list(inspector.get_table_names())
    return sorted(set(tables))


def execute_select_sql(engine, sql_query: str, provider: str) -> pd.DataFrame:
    ok, err = validate_select_sql(sql_query)
    if not ok:
        raise ValueError(err)
    sql_query = enforce_row_limit(sql_query, int(settings.MAX_SQL_RESULT_ROWS))
    with engine.connect() as conn:
        if provider in MYSQL_FAMILY:
            conn.execute(text(f"SET SESSION MAX_EXECUTION_TIME={int(settings.SQL_QUERY_TIMEOUT_SECONDS) * 1000}"))
        return pd.read_sql_query(sql_query, conn)


def effective_row_cap(sql_query: str) -> int:
    """Upper bound on rows this query may return after enforce_row_limit."""
    capped = enforce_row_limit(sql_query, int(settings.MAX_SQL_RESULT_ROWS))
    match = re.search(r"\blimit\s+(\d+)\s*$", capped.lower())
    return int(match.group(1)) if match else int(settings.MAX_SQL_RESULT_ROWS)


def stream_select_to_csv(engine, sql_query: str, provider: str, output_path: str) -> int:
    """Stream SELECT results to a CSV file; returns total row count."""
    ok, err = validate_select_sql(sql_query)
    if not ok:
        raise ValueError(err)
    sql_query = enforce_row_limit(sql_query, int(settings.MAX_SQL_RESULT_ROWS))
    chunk_size = max(1000, int(settings.SQL_STREAM_CHUNK_SIZE))
    row_count = 0
    with engine.connect() as conn:
        if provider in MYSQL_FAMILY:
            conn.execute(text(f"SET SESSION MAX_EXECUTION_TIME={int(settings.SQL_QUERY_TIMEOUT_SECONDS) * 1000}"))
        first = True
        for chunk in pd.read_sql_query(sql_query, conn, chunksize=chunk_size):
            chunk.to_csv(
                output_path,
                mode="a",
                index=False,
                header=first,
                encoding="utf-8-sig",
            )
            row_count += len(chunk)
            first = False
    return row_count


def execute_select_to_handle(engine, sql_query: str, provider: str) -> DatasetHandle:
    """Run SELECT and return a DatasetHandle without holding a large DataFrame when possible."""
    cap = effective_row_cap(sql_query)
    if cap < settings.DUCKDB_ROW_THRESHOLD:
        df = execute_select_sql(engine, sql_query, provider)
        return DatasetHandle.from_dataframe(df)

    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            path = tmp.name
        row_count = stream_select_to_csv(engine, sql_query, provider, path)
        if row_count == 0:
            return DatasetHandle.from_dataframe(pd.DataFrame())
        con = duckdb.connect()
        esc = path.replace("'", "''")
        con.execute(f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM read_csv_auto('{esc}')")
        if row_count >= settings.DUCKDB_ROW_THRESHOLD:
            return DatasetHandle(
                con=con,
                table=TABLE_NAME,
                is_duckdb_primary=True,
                cached_row_count=row_count,
            )
        df = con.execute(f"SELECT * FROM {TABLE_NAME}").df()
        return DatasetHandle.from_dataframe(df)
    finally:
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass


def enforce_row_limit(sql_query: str, max_rows: int) -> str:
    """Append or clamp LIMIT on SELECT queries."""
    cleaned = (sql_query or "").strip().rstrip(";")
    lower = cleaned.lower()
    match = re.search(r"\blimit\s+(\d+)\s*$", lower)
    if match:
        existing = int(match.group(1))
        if existing > max_rows:
            cleaned = re.sub(r"\blimit\s+\d+\s*$", f"LIMIT {max_rows}", cleaned, flags=re.IGNORECASE)
        return cleaned
    return f"{cleaned} LIMIT {max_rows}"
