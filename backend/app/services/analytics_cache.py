"""Analytics result cache — in-memory L1 + disk L2 (survives restarts, shareable across workers)."""
import hashlib
import json
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.json_safety import json_safe_dumps, to_json_safe

_lock = Lock()
_base_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
_question_cache: Dict[str, tuple[float, Any]] = {}


def _ttl() -> float:
    return float(settings.ANALYTICS_CACHE_TTL_SECONDS)


def _hash_parts(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _disk_root() -> Path:
    raw = Path(settings.ANALYTICS_DISK_CACHE_DIR)
    if raw.is_absolute():
        path = raw
    else:
        backend_root = Path(__file__).resolve().parent.parent.parent
        path = backend_root / raw
    path.mkdir(parents=True, exist_ok=True)
    return path


def _disk_path(prefix: str, key: str) -> Path:
    return _disk_root() / f"{prefix}_{key}.json"


def mapping_hash(column_mapping: Optional[Dict[str, str]]) -> str:
    return _hash_parts(column_mapping or {})


def base_cache_key(
    user_id: str,
    file_name: Optional[str],
    column_mapping: Optional[Dict[str, str]],
    connection_id: Optional[str] = None,
    cleaning_profile: str = "standard",
    provenance: Optional[Dict[str, Any]] = None,
) -> str:
    return _hash_parts(
        "base",
        user_id,
        file_name or "",
        connection_id or "",
        mapping_hash(column_mapping),
        (cleaning_profile or "standard").strip().lower(),
        provenance or {},
    )


def question_cache_key(
    user_id: str,
    file_name: Optional[str],
    column_mapping: Optional[Dict[str, str]],
    question: str,
    connection_id: Optional[str] = None,
    cleaning_profile: str = "standard",
    provenance: Optional[Dict[str, Any]] = None,
) -> str:
    q = (question or "").strip().lower()
    return _hash_parts(
        "q",
        user_id,
        file_name or "",
        connection_id or "",
        mapping_hash(column_mapping),
        (cleaning_profile or "standard").strip().lower(),
        provenance or {},
        q,
    )


def _get(cache: Dict[str, tuple[float, Any]], key: str) -> Optional[Any]:
    with _lock:
        entry = cache.get(key)
        if not entry:
            return None
        ts, val = entry
        if time.time() - ts > _ttl():
            del cache[key]
            return None
        return val


def _set(cache: Dict[str, tuple[float, Any]], key: str, val: Any) -> None:
    with _lock:
        cache[key] = (time.time(), val)


def _read_disk(prefix: str, key: str) -> Optional[Any]:
    path = _disk_path(prefix, key)
    if not path.exists():
        return None
    try:
        mtime = path.stat().st_mtime
        if time.time() - mtime > _ttl():
            path.unlink(missing_ok=True)
            return None
        with open(path, encoding="utf-8") as handle:
            return to_json_safe(json.load(handle))
    except (OSError, json.JSONDecodeError):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def _write_disk(prefix: str, key: str, val: Any) -> None:
    path = _disk_path(prefix, key)
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(json_safe_dumps(val, ensure_ascii=False, default=str))
        tmp.replace(path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def get_base_analytics(key: str) -> Optional[Dict[str, Any]]:
    val = _get(_base_cache, key)
    if val is not None:
        return val
    disk_val = _read_disk("base", key)
    if disk_val is not None:
        _set(_base_cache, key, disk_val)
    return disk_val


def set_base_analytics(key: str, val: Dict[str, Any]) -> None:
    _set(_base_cache, key, val)
    _write_disk("base", key, val)


def get_question_result(key: str) -> Optional[Any]:
    val = _get(_question_cache, key)
    if val is not None:
        return val
    disk_val = _read_disk("q", key)
    if disk_val is not None:
        _set(_question_cache, key, disk_val)
    return disk_val


def set_question_result(key: str, val: Any) -> None:
    _set(_question_cache, key, val)
    _write_disk("q", key, val)
