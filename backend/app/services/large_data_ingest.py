"""Memory-efficient ingest for Excel, JSON, and API tabular payloads into DatasetHandle."""
import io
import json
import os
import tempfile
from typing import Any, List, Mapping, Optional

import duckdb
import pandas as pd

from app.core.config import settings
from app.core.parser import (
    detect_header_row_from_path,
    detect_header_row_from_bytes,
    select_excel_sheet_from_path,
    select_excel_sheet_from_bytes,
)
from app.services.dataset_engine import TABLE_NAME, DatasetHandle
from app.services.file_validation import validate_upload_bytes
from app.services.json_structure import flatten_json_to_records
from app.services.json_paths import resolve_record_path


def _escape_path(path: str) -> str:
    return path.replace("'", "''")


def _excel_xlsx_to_ndjson(
    xlsx_path: str,
    ndjson_path: str,
    header_row: int = 0,
    sheet_name: Optional[str] = None,
) -> int:
    """Stream .xlsx rows to NDJSON via openpyxl read_only (constant memory)."""
    from openpyxl import load_workbook

    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    try:
        ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active
        row_iter = ws.iter_rows(values_only=True)
        for _ in range(max(0, int(header_row))):
            next(row_iter, None)
        header = next(row_iter, None)
        if not header:
            return 0
        cols = [
            str(h).strip() if h is not None and str(h).strip() else f"col_{i}"
            for i, h in enumerate(header)
        ]
        count = 0
        with open(ndjson_path, "w", encoding="utf-8") as out:
            for row in row_iter:
                if row is None or all(c is None or str(c).strip() == "" for c in row):
                    continue
                rec = {
                    cols[i]: row[i] if i < len(row) else None
                    for i in range(len(cols))
                }
                out.write(json.dumps(rec, ensure_ascii=False, default=str))
                out.write("\n")
                count += 1
        return count
    finally:
        wb.close()


def _column_filter_sql(target_cols: Optional[List[str]], con: duckdb.DuckDBPyConnection) -> None:
    if not target_cols:
        return
    available = {r[0] for r in con.execute(f"DESCRIBE {TABLE_NAME}").fetchall()}
    valid = [c for c in target_cols if c in available]
    if not valid:
        return
    quoted = ", ".join('"' + c.replace('"', '""') + '"' for c in valid)
    sel = f"{TABLE_NAME}_sel"
    con.execute(f"CREATE TABLE {sel} AS SELECT {quoted} FROM {TABLE_NAME}")
    con.execute(f"DROP TABLE {TABLE_NAME}")
    con.execute(f"ALTER TABLE {sel} RENAME TO {TABLE_NAME}")


def _handle_from_registered_table(con: duckdb.DuckDBPyConnection, row_count: int) -> DatasetHandle:
    if row_count >= settings.DUCKDB_ROW_THRESHOLD:
        return DatasetHandle(
            con=con,
            table=TABLE_NAME,
            is_duckdb_primary=True,
            cached_row_count=row_count,
        )
    df = con.execute(f"SELECT * FROM {TABLE_NAME}").df()
    return DatasetHandle.from_dataframe(df)


def records_to_handle(
    records: List[dict],
    target_cols: Optional[List[str]] = None,
) -> Optional[DatasetHandle]:
    if not records:
        return None
    n = len(records)
    if n < settings.DUCKDB_ROW_THRESHOLD:
        df = pd.DataFrame(records)
        if target_cols:
            valid = [c for c in target_cols if c in df.columns]
            if valid:
                df = df[valid]
        return DatasetHandle.from_dataframe(df)

    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".ndjson", delete=False) as tmp:
            path = tmp.name
        with open(path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False, default=str))
                f.write("\n")
        con = duckdb.connect()
        con.execute(
            f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM read_json_auto('{_escape_path(path)}')"
        )
        _column_filter_sql(target_cols, con)
        return _handle_from_registered_table(con, n)
    finally:
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass


def ingest_json_path(
    path: str,
    target_cols: Optional[List[str]] = None,
    json_path: Optional[str] = None,
) -> Optional[DatasetHandle]:
    """Ingest JSON/NDJSON via DuckDB read_json_auto without loading full payload into Python."""
    if json_path:
        try:
            with open(path, encoding="utf-8") as source:
                records = resolve_record_path(json.load(source), json_path)
            return records_to_handle(records, target_cols)
        except (OSError, json.JSONDecodeError):
            return None
    con = duckdb.connect()
    esc = _escape_path(path)
    try:
        con.execute(f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM read_json_auto('{esc}')")
        count = int(con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0])
        _column_filter_sql(target_cols, con)
        count = int(con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0])
        return _handle_from_registered_table(con, count)
    except Exception as e:
        print(f"read_json_auto failed for {path}: {e}")
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None
        return ingest_json_value(data, target_cols)


def ingest_json_value(
    json_data: Any,
    target_cols: Optional[List[str]] = None,
) -> Optional[DatasetHandle]:
    records = flatten_json_to_records(json_data)
    if records:
        return records_to_handle(records, target_cols)
    if isinstance(json_data, dict):
        return records_to_handle([json_data], target_cols)
    return None


def ingest_api_connection(
    conn: Mapping[str, Any],
    target_cols: Optional[List[str]] = None,
) -> Optional[DatasetHandle]:
    """Ingest API connection payload; paginated when ``_pagination`` is configured."""
    from app.services.api_pagination import get_pagination_config, stream_api_records_to_ndjson

    ndjson_path = None
    try:
        if get_pagination_config(conn):
            with tempfile.NamedTemporaryFile(suffix=".ndjson", delete=False) as tmp:
                ndjson_path = tmp.name
            count = stream_api_records_to_ndjson(conn, ndjson_path)
            if count == 0:
                return None
            return ingest_json_path(ndjson_path, target_cols)
        from app.services.api_pagination import fetch_connection_json

        return ingest_json_value(fetch_connection_json(conn), target_cols)
    finally:
        if ndjson_path and os.path.exists(ndjson_path):
            try:
                os.unlink(ndjson_path)
            except OSError:
                pass


def ingest_json_bytes(
    file_bytes: bytes,
    target_cols: Optional[List[str]] = None,
    json_path: Optional[str] = None,
) -> Optional[DatasetHandle]:
    try:
        data = json.loads(file_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    records = resolve_record_path(data, json_path) if json_path else None
    return records_to_handle(records, target_cols) if records else ingest_json_value(data, target_cols)


def ingest_excel_path(
    path: str,
    target_cols: Optional[List[str]] = None,
) -> Optional[DatasetHandle]:
    size = os.path.getsize(path)
    ext = path.rsplit(".", 1)[-1].lower()
    use_streaming = ext == "xlsx" and size >= settings.EXCEL_STREAMING_BYTES_THRESHOLD

    if use_streaming:
        ndjson_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".ndjson", delete=False) as tmp:
                ndjson_path = tmp.name
            sheet_name = select_excel_sheet_from_path(path)
            header_row = detect_header_row_from_path(path, os.path.basename(path))
            row_count = _excel_xlsx_to_ndjson(path, ndjson_path, header_row, sheet_name)
            if row_count == 0:
                return None
            handle = ingest_json_path(ndjson_path, target_cols)
            return handle
        except Exception as e:
            print(f"Streaming Excel ingest failed, falling back to pandas: {e}")
        finally:
            if ndjson_path and os.path.exists(ndjson_path):
                try:
                    os.unlink(ndjson_path)
                except OSError:
                    pass

    sheet_name = select_excel_sheet_from_path(path)
    header_row = detect_header_row_from_path(path, os.path.basename(path))
    frame = pd.read_excel(path, sheet_name=sheet_name, header=header_row)
    if target_cols:
        valid = [c for c in target_cols if c in frame.columns]
        if valid:
            frame = frame[valid]
    n = len(frame)
    if n < settings.DUCKDB_ROW_THRESHOLD:
        return DatasetHandle.from_dataframe(frame)

    parquet_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            parquet_path = tmp.name
        frame.to_parquet(parquet_path, index=False)
        del frame
        con = duckdb.connect()
        con.execute(
            f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM read_parquet('{_escape_path(parquet_path)}')"
        )
        return DatasetHandle(
            con=con,
            table=TABLE_NAME,
            is_duckdb_primary=True,
            cached_row_count=n,
        )
    except Exception as e:
        print(f"Excel parquet ingest failed, falling back to DataFrame: {e}")
        frame = pd.read_excel(path, sheet_name=sheet_name, header=header_row)
        if target_cols:
            valid = [c for c in target_cols if c in frame.columns]
            if valid:
                frame = frame[valid]
        return DatasetHandle.from_dataframe(frame)
    finally:
        if parquet_path and os.path.exists(parquet_path):
            try:
                os.unlink(parquet_path)
            except OSError:
                pass


def ingest_excel_bytes(
    file_bytes: bytes,
    target_cols: Optional[List[str]] = None,
    file_name: str = "upload.xlsx",
) -> Optional[DatasetHandle]:
    validate_upload_bytes(file_name, len(file_bytes))
    ext = file_name.rsplit(".", 1)[-1].lower()
    if ext == "xlsx" and len(file_bytes) >= settings.EXCEL_STREAMING_BYTES_THRESHOLD:
        xlsx_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                xlsx_path = tmp.name
                tmp.write(file_bytes)
            return ingest_excel_path(xlsx_path, target_cols)
        finally:
            if xlsx_path and os.path.exists(xlsx_path):
                try:
                    os.unlink(xlsx_path)
                except OSError:
                    pass

    sheet_name = select_excel_sheet_from_bytes(file_bytes)
    header_row = detect_header_row_from_bytes(file_bytes, file_name)
    frame = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=header_row)
    if target_cols:
        valid = [c for c in target_cols if c in frame.columns]
        if valid:
            frame = frame[valid]
    n = len(frame)
    if n < settings.DUCKDB_ROW_THRESHOLD:
        return DatasetHandle.from_dataframe(frame)

    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            path = tmp.name
        frame.to_parquet(path, index=False)
        del frame
        con = duckdb.connect()
        con.execute(
            f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM read_parquet('{_escape_path(path)}')"
        )
        return DatasetHandle(
            con=con,
            table=TABLE_NAME,
            is_duckdb_primary=True,
            cached_row_count=n,
        )
    except Exception as e:
        print(f"Excel parquet ingest failed, falling back to DataFrame: {e}")
        frame = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=header_row)
        if target_cols:
            valid = [c for c in target_cols if c in frame.columns]
            if valid:
                frame = frame[valid]
        return DatasetHandle.from_dataframe(frame)
    finally:
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass
