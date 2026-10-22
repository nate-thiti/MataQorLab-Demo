"""Safe selection of tabular record arrays inside nested JSON documents."""
from __future__ import annotations

from typing import Any, List, Optional


def discover_record_paths(value: Any, *, max_depth: int = 6, max_paths: int = 30) -> List[str]:
    paths: List[str] = []

    def walk(node: Any, path: str, depth: int) -> None:
        if len(paths) >= max_paths or depth > max_depth:
            return
        if isinstance(node, list):
            if node and all(isinstance(item, dict) for item in node[:20]):
                paths.append(f"{path}[]" if path else "[]")
            for item in node[:3]:
                if isinstance(item, (dict, list)):
                    walk(item, f"{path}[]" if path else "[]", depth + 1)
        elif isinstance(node, dict):
            for key, item in node.items():
                next_path = f"{path}.{key}" if path else str(key)
                if isinstance(item, (dict, list)):
                    walk(item, next_path, depth + 1)

    walk(value, "", 0)
    return list(dict.fromkeys(paths))


def resolve_record_path(value: Any, path: Optional[str]) -> List[dict]:
    """Resolve `items[]` / `data.rows[]` into records; reject arbitrary syntax."""
    if not path:
        return []
    current: List[Any] = [value]
    for part in path.split("."):
        is_array = part.endswith("[]")
        key = part[:-2] if is_array else part
        if not key and part != "[]":
            return []
        next_values: List[Any] = []
        for item in current:
            child = item if part == "[]" else (item.get(key) if isinstance(item, dict) else None)
            if is_array:
                if isinstance(child, list):
                    next_values.extend(child)
            elif child is not None:
                next_values.append(child)
        current = next_values
        if not current:
            return []
    return [item for item in current if isinstance(item, dict)]
