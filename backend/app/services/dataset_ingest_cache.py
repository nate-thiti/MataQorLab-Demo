"""Disk cache for ingested DuckDB datasets — avoids re-download/re-ingest on every chat."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import duckdb

from app.core.config import settings
from app.services.dataset_engine import TABLE_NAME, DatasetHandle, open_persisted_duckdb_handle
from app.services.storage_download import get_storage_object_size


def _cache_root() -> Path:
    raw = Path(settings.DATASET_INGEST_CACHE_DIR)
    if raw.is_absolute():
        path = raw
    else:
        backend_root = Path(__file__).resolve().parent.parent.parent
        path = backend_root / raw
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_key(
    user_id: str,
    file_name: str,
    file_size: int,
    source_fingerprint: Optional[str] = None,
) -> str:
    raw = f"{user_id}|{file_name}|{file_size}|{source_fingerprint or ''}".encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def _cache_path(key: str) -> Path:
    return _cache_root() / f"{key}.duckdb"


def lookup_storage_size(user_id: str, file_name: str) -> Optional[int]:
    return get_storage_object_size(
        settings.AGENT_SESSION_STORAGE_BUCKET,
        f"{user_id}/{file_name}",
    )


def _summary_sidecar_path(cache_path: Path) -> Path:
    return cache_path.with_suffix(".summary.json")


def _persist_summary_sidecar(cache_path: Path, handle: DatasetHandle) -> None:
    """Materialized SUMMARIZE stats — skip expensive re-scan on cache hit."""
    sidecar = _summary_sidecar_path(cache_path)
    try:
        summary_df = handle.summarize_df()
        sidecar.write_text(summary_df.to_json(orient="records"), encoding="utf-8")
    except Exception as e:
        print(f"Dataset summary sidecar persist failed: {e}")
        try:
            sidecar.unlink(missing_ok=True)
        except OSError:
            pass


def _load_summary_sidecar(cache_path: Path, handle: DatasetHandle) -> None:
    sidecar = _summary_sidecar_path(cache_path)
    if not sidecar.exists():
        return
    try:
        import pandas as pd

        summary_df = pd.read_json(sidecar, orient="records")
        handle._summarize_df = summary_df
    except Exception:
        try:
            sidecar.unlink(missing_ok=True)
        except OSError:
            pass


def try_load_cached_handle(
    user_id: str,
    file_name: str,
    file_size: int,
    source_fingerprint: Optional[str] = None,
) -> Optional[DatasetHandle]:
    path = _cache_path(_cache_key(user_id, file_name, file_size, source_fingerprint))
    if not path.exists():
        return None
    try:
        handle = open_persisted_duckdb_handle(str(path))
        if handle is None:
            raise RuntimeError("attach failed")
        _load_summary_sidecar(path, handle)
        handle._source_fingerprint = source_fingerprint
        return handle
    except Exception as e:
        print(f"Dataset ingest cache load failed ({path}): {e}")
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def persist_ingest_cache(
    user_id: str,
    file_name: str,
    file_size: int,
    handle: DatasetHandle,
    source_fingerprint: Optional[str] = None,
) -> None:
    if handle.row_count() == 0:
        return
    path = _cache_path(_cache_key(user_id, file_name, file_size, source_fingerprint))
    tmp_pq = path.with_suffix(".export.parquet")
    esc_pq = str(tmp_pq).replace("'", "''")
    try:
        # Small handles retain a Pandas frame and intentionally do not register
        # a DuckDB relation until SQL execution. Register it before COPY so
        # cache persistence works for both small and large datasets.
        if handle._df is not None:
            handle._con.register(TABLE_NAME, handle._df)
        handle._con.execute(
            f"COPY (SELECT * FROM {handle._table}) TO '{esc_pq}' (FORMAT PARQUET)"
        )
        if path.exists():
            path.unlink()
        persist_con = duckdb.connect(str(path))
        persist_con.execute(
            f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM read_parquet('{esc_pq}')"
        )
        persist_con.close()
        _persist_summary_sidecar(path, handle)
    except Exception as e:
        print(f"Dataset ingest cache persist failed: {e}")
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    finally:
        if tmp_pq.exists():
            try:
                tmp_pq.unlink()
            except OSError:
                pass
