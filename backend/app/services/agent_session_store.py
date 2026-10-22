"""
Agent session store for pause/resume during multi-step analysis.
Backends: local file (default) or Supabase table + Storage (multi-instance).
"""
import duckdb
import io
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.core.config import settings

SESSION_TTL_SECONDS = 1800  # 30 minutes

_sessions: Dict[str, tuple["AgentSession", float]] = {}
_fallback_session_dir: Optional[Path] = None
_logger = logging.getLogger(__name__)


def _use_supabase() -> bool:
    return (settings.AGENT_SESSION_BACKEND or "file").lower() == "supabase"


def _resolve_session_base() -> Path:
    raw = Path(settings.AGENT_SESSION_DIR)
    if raw.is_absolute():
        return raw
    backend_root = Path(__file__).resolve().parent.parent.parent
    return backend_root / raw


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _session_dir() -> Path:
    global _fallback_session_dir
    if _fallback_session_dir is not None:
        return _fallback_session_dir

    base = _resolve_session_base()
    if _is_writable_dir(base):
        return base

    fallback = Path(__file__).resolve().parent.parent.parent / ".local" / "agent_sessions"
    if not _is_writable_dir(fallback):
        raise PermissionError(
            f"Agent session directory is not writable: {base} "
            f"(fallback also failed: {fallback})"
        )

    _fallback_session_dir = fallback
    _logger.warning(
        "AGENT_SESSION_DIR %s is not writable; using fallback %s",
        base,
        fallback,
    )
    return fallback


def _session_json_path(session_id: str) -> Path:
    return _session_dir() / f"{session_id}.json"


def _session_parquet_path(session_id: str) -> Path:
    return _session_dir() / f"{session_id}.parquet"


def _session_duckdb_path(session_id: str) -> Path:
    return _session_dir() / f"{session_id}.duckdb"


@dataclass
class AgentSession:
    session_id: str
    user_id: str
    status: str  # paused | running | completed
    original_question: str
    file_attachment_name: Optional[str] = None
    connection_id: Optional[str] = None
    connection_type: Optional[str] = None
    sql_table: Optional[str] = None
    sql_query: Optional[str] = None
    column_mapping: Optional[Dict[str, str]] = None
    analytics_results: Optional[Dict[str, Any]] = None
    dataset_type: Optional[str] = None
    summary: Optional[str] = None
    source_fingerprint: Optional[str] = None
    contract_hash: Optional[str] = None
    recipe_hash: Optional[str] = None
    dataset_version_id: Optional[str] = None
    data_contract: Optional[Dict[str, Any]] = None
    planned_steps: List[str] = field(default_factory=list)
    planned_tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    completed_steps: List[Dict[str, Any]] = field(default_factory=list)
    tool_call_ledger: List[Dict[str, Any]] = field(default_factory=list)
    agent_decisions: List[Dict[str, Any]] = field(default_factory=list)
    agent_stop_reason: Optional[str] = None
    current_step_index: int = 0
    pending_clarification: Optional[str] = None
    clarification_reason: Optional[str] = None
    pending_tool_approval: Optional[Dict[str, Any]] = None
    user_clarifications: List[Dict[str, str]] = field(default_factory=list)
    model: str = ""
    planning_done: bool = False
    df_parquet: Optional[bytes] = None
    parquet_storage_path: Optional[str] = None
    duckdb_local_path: Optional[str] = None
    duckdb_storage_path: Optional[str] = None
    updated_at: float = 0.0


@dataclass
class AgentPauseResult:
    session_id: str
    question: str
    reason: Optional[str] = None


def _session_to_dict(session: AgentSession) -> Dict[str, Any]:
    data = asdict(session)
    data.pop("df_parquet", None)
    return data


def _session_from_dict(data: Dict[str, Any]) -> AgentSession:
    data = dict(data)
    data.pop("df_parquet", None)
    return AgentSession(df_parquet=None, **data)


def _persist_session_file(session: AgentSession) -> None:
    session.updated_at = time.time()
    path = _session_json_path(session.session_id)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_session_to_dict(session), f, ensure_ascii=False, default=str)
    os.replace(tmp, path)
    _sessions[session.session_id] = (session, session.updated_at)


def _persist_session_supabase(session: AgentSession) -> None:
    from app.core.supabase import get_supabase_client

    session.updated_at = time.time()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)
    supabase = get_supabase_client()
    row = {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "session_data": _session_to_dict(session),
        "parquet_path": session.parquet_storage_path,
        "expires_at": expires_at.isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    supabase.table("agent_sessions").upsert(row, on_conflict="session_id").execute()
    _sessions[session.session_id] = (session, session.updated_at)


def _persist_session(session: AgentSession) -> None:
    if _use_supabase():
        _persist_session_supabase(session)
    else:
        _persist_session_file(session)


def _load_session_from_disk(session_id: str) -> Optional[AgentSession]:
    path = _session_json_path(session_id)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        session = _session_from_dict(data)
        updated = session.updated_at or path.stat().st_mtime
        if time.time() - updated > SESSION_TTL_SECONDS:
            delete_session(session_id)
            return None
        _sessions[session_id] = (session, updated)
        return session
    except Exception as e:
        print(f"Failed to load agent session {session_id}: {e}")
        return None


def _load_session_from_supabase(session_id: str, user_id: str) -> Optional[AgentSession]:
    from app.core.supabase import get_supabase_client

    try:
        supabase = get_supabase_client()
        res = (
            supabase.table("agent_sessions")
            .select("*")
            .eq("session_id", session_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if not res.data:
            return None
        row = res.data
        expires = row.get("expires_at")
        if expires:
            exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if exp_dt < datetime.now(timezone.utc):
                delete_session(session_id)
                return None
        data = row.get("session_data") or {}
        session = _session_from_dict(data)
        session.parquet_storage_path = row.get("parquet_path") or session.parquet_storage_path
        _sessions[session_id] = (session, session.updated_at or time.time())
        return session
    except Exception as e:
        print(f"Failed to load agent session from Supabase {session_id}: {e}")
        return None


def _purge_expired() -> None:
    now = time.time()
    expired = [sid for sid, (_, ts) in _sessions.items() if now - ts > SESSION_TTL_SECONDS]
    for sid in expired:
        delete_session(sid)

    if _use_supabase():
        try:
            from app.core.supabase import get_supabase_client
            supabase = get_supabase_client()
            supabase.table("agent_sessions").delete().lt(
                "expires_at", datetime.now(timezone.utc).isoformat()
            ).execute()
        except Exception as e:
            print(f"Agent session Supabase purge failed: {e}")
        return

    session_dir = _session_dir()
    for json_path in session_dir.glob("*.json"):
        try:
            if now - json_path.stat().st_mtime > SESSION_TTL_SECONDS:
                delete_session(json_path.stem)
        except OSError:
            continue


def create_session(user_id: str, **kwargs) -> AgentSession:
    _purge_expired()
    session_id = str(uuid.uuid4())
    status = kwargs.pop("status", "paused")
    original_question = kwargs.pop("original_question", "")
    session = AgentSession(
        session_id=session_id,
        user_id=user_id,
        status=status,
        original_question=original_question,
        updated_at=time.time(),
        **kwargs,
    )
    _persist_session(session)
    return session


def get_session(session_id: str, user_id: str) -> Optional[AgentSession]:
    _purge_expired()
    entry = _sessions.get(session_id)
    session: Optional[AgentSession] = None
    ts = 0.0
    if entry:
        session, ts = entry
    elif _use_supabase():
        session = _load_session_from_supabase(session_id, user_id)
        if session:
            ts = session.updated_at or time.time()
    else:
        session = _load_session_from_disk(session_id)
        if session:
            ts = session.updated_at or time.time()

    if not session:
        return None
    if time.time() - ts > SESSION_TTL_SECONDS:
        delete_session(session_id)
        return None
    if session.user_id != user_id:
        return None
    _sessions[session_id] = (session, time.time())
    return session


def update_session(session: AgentSession) -> None:
    _persist_session(session)


def delete_session(session_id: str) -> None:
    session_entry = _sessions.get(session_id)
    session = session_entry[0] if session_entry else None

    _sessions.pop(session_id, None)

    if _use_supabase():
        try:
            from app.core.supabase import get_supabase_client
            supabase = get_supabase_client()
            if session and session.parquet_storage_path:
                try:
                    supabase.storage.from_(settings.AGENT_SESSION_STORAGE_BUCKET).remove(
                        [session.parquet_storage_path]
                    )
                except Exception:
                    pass
            if session and session.duckdb_storage_path:
                try:
                    supabase.storage.from_(settings.AGENT_SESSION_STORAGE_BUCKET).remove(
                        [session.duckdb_storage_path]
                    )
                except Exception:
                    pass
            supabase.table("agent_sessions").delete().eq("session_id", session_id).execute()
        except Exception as e:
            print(f"Agent session Supabase delete failed: {e}")
        return

    try:
        _session_json_path(session_id).unlink(missing_ok=True)
    except OSError:
        pass
    try:
        _session_parquet_path(session_id).unlink(missing_ok=True)
    except OSError:
        pass
    try:
        _session_duckdb_path(session_id).unlink(missing_ok=True)
    except OSError:
        pass


def cache_handle_for_session(session: AgentSession, handle: "DatasetHandle") -> None:
    """Persist dataset for agent pause/resume — DuckDB file for large, parquet for small."""
    from app.services.dataset_engine import DatasetHandle

    if not isinstance(handle, DatasetHandle):
        return
    if handle.is_large:
        _cache_large_handle_duckdb(session, handle)
    else:
        cache_df_for_session(session, handle.to_pandas())


def _cache_large_handle_duckdb(session: AgentSession, handle: "DatasetHandle") -> None:
    from app.services.dataset_engine import TABLE_NAME

    db_path = _session_duckdb_path(session.session_id)
    tmp_pq = db_path.with_suffix(".export.parquet")
    esc_pq = str(tmp_pq).replace("'", "''")
    try:
        handle._con.execute(
            f"COPY (SELECT * FROM {handle._table}) TO '{esc_pq}' (FORMAT PARQUET)"
        )
        if db_path.exists():
            db_path.unlink()
        persist_con = duckdb.connect(str(db_path))
        persist_con.execute(
            f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM read_parquet('{esc_pq}')"
        )
        persist_con.close()
        session.duckdb_local_path = str(db_path)

        if _use_supabase():
            from app.core.supabase import get_supabase_client

            storage_path = f"{session.user_id}/agent_sessions/{session.session_id}.duckdb"
            supabase = get_supabase_client()
            from app.services.storage_quota import enforce_customer_storage_quota
            enforce_customer_storage_quota(
                session.user_id, os.path.getsize(db_path), storage_path
            )
            with open(db_path, "rb") as db_file:
                supabase.storage.from_(settings.AGENT_SESSION_STORAGE_BUCKET).upload(
                    storage_path,
                    db_file,
                    {"content-type": "application/octet-stream", "upsert": "true"},
                )
            session.duckdb_storage_path = storage_path

        update_session(session)
    except Exception as e:
        print(f"DuckDB session cache failed: {e}")
    finally:
        if tmp_pq.exists():
            try:
                tmp_pq.unlink()
            except OSError:
                pass


def load_handle_from_session(session: AgentSession) -> Optional["DatasetHandle"]:
    """Restore DatasetHandle from persisted DuckDB file or small parquet cache."""
    from app.services.dataset_engine import DatasetHandle, open_persisted_duckdb_handle

    local_path = session.duckdb_local_path or str(_session_duckdb_path(session.session_id))
    if local_path and os.path.exists(local_path):
        handle = open_persisted_duckdb_handle(local_path, is_duckdb_primary=True)
        if handle is not None:
            return handle
        print(f"DuckDB session load failed ({local_path})")

    if session.duckdb_storage_path and _use_supabase():
        from app.services.storage_download import download_storage_path_safe

        data = download_storage_path_safe(
            settings.AGENT_SESSION_STORAGE_BUCKET,
            session.duckdb_storage_path,
        )
        if data is not None:
            db_path = _session_duckdb_path(session.session_id)
            try:
                tmp = db_path.with_suffix(".tmp")
                with open(tmp, "wb") as out:
                    out.write(data)
                os.replace(tmp, db_path)
                session.duckdb_local_path = str(db_path)
                handle = open_persisted_duckdb_handle(str(db_path), is_duckdb_primary=True)
                if handle is not None:
                    return handle
                print(f"DuckDB session load from Supabase failed ({db_path})")
            except Exception as e:
                print(f"DuckDB session load from Supabase failed: {e}")

    df = load_df_from_session(session)
    if df is not None and not df.empty:
        return DatasetHandle.from_dataframe(df)
    return None


def cache_df_for_session(session: AgentSession, df: pd.DataFrame) -> None:
    max_bytes = settings.AGENT_DF_CACHE_MAX_MB * 1024 * 1024
    try:
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        size = buf.tell()
        if size > max_bytes:
            print(
                f"Agent session DF cache skipped ({size} bytes > {max_bytes}); "
                "will reload from source on resume."
            )
            return
        data = buf.getvalue()
        session.df_parquet = data

        if _use_supabase():
            from app.core.supabase import get_supabase_client
            storage_path = f"{session.user_id}/agent_sessions/{session.session_id}.parquet"
            supabase = get_supabase_client()
            from app.services.storage_quota import enforce_customer_storage_quota
            enforce_customer_storage_quota(session.user_id, len(data), storage_path)
            supabase.storage.from_(settings.AGENT_SESSION_STORAGE_BUCKET).upload(
                storage_path,
                data,
                {"content-type": "application/octet-stream", "upsert": "true"},
            )
            session.parquet_storage_path = storage_path
            update_session(session)
            return

        parquet_path = _session_parquet_path(session.session_id)
        tmp = parquet_path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, parquet_path)
        update_session(session)
    except Exception as e:
        print(f"DF cache for agent session failed: {e}")


def load_df_from_session(session: AgentSession) -> Optional[pd.DataFrame]:
    if session.df_parquet:
        try:
            return pd.read_parquet(io.BytesIO(session.df_parquet))
        except Exception as e:
            print(f"DF load from agent session memory failed: {e}")

    if session.parquet_storage_path and _use_supabase():
        from app.services.storage_download import download_storage_path_safe

        data = download_storage_path_safe(
            settings.AGENT_SESSION_STORAGE_BUCKET,
            session.parquet_storage_path,
        )
        if data is not None:
            try:
                return pd.read_parquet(io.BytesIO(data))
            except Exception as e:
                print(f"DF load from Supabase storage failed: {e}")

    parquet_path = _session_parquet_path(session.session_id)
    if not parquet_path.exists():
        return None
    try:
        return pd.read_parquet(parquet_path)
    except Exception as e:
        print(f"DF load from agent session disk failed: {e}")
        return None
