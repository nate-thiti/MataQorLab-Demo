"""Heuristic JSON structure summaries for non-tabular payloads (no raw dump to LLM)."""
from typing import Any, List


def summarize_json_structure(data: Any, max_depth: int = 3, max_keys: int = 12) -> str:
    def _summarize(obj: Any, depth: int = 0) -> str:
        if depth > max_depth:
            return "…"
        if isinstance(obj, list):
            if not obj:
                return "empty array"
            n = len(obj)
            sample = obj[:20]
            if all(isinstance(x, dict) for x in sample):
                keys: set[str] = set()
                for item in sample:
                    keys.update(item.keys())
                key_list = sorted(keys)[:max_keys]
                extra = f" (+{len(keys) - max_keys} more)" if len(keys) > max_keys else ""
                return f"array[{n}] of objects — keys: {', '.join(key_list)}{extra}"
            types = sorted({type(x).__name__ for x in sample[:5]})
            return f"array[{n}], element types: {', '.join(types)}"
        if isinstance(obj, dict):
            keys = list(obj.keys())
            parts: List[str] = []
            for k in keys[:max_keys]:
                v = obj[k]
                if isinstance(v, (list, dict)):
                    parts.append(f"{k}: {_summarize(v, depth + 1)}")
                else:
                    parts.append(f"{k}: {type(v).__name__}")
            extra = f" (+{len(keys) - max_keys} more keys)" if len(keys) > max_keys else ""
            return f"object ({len(keys)} keys) — " + "; ".join(parts) + extra
        return f"{type(obj).__name__}: {str(obj)[:80]}"

    return _summarize(data)


def flatten_json_to_records(data: Any) -> list[dict]:
    """Extract tabular row objects from common JSON API shapes."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return [x for x in value if isinstance(x, dict)]
        return [data]
    return []
