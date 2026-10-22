"""Safe arithmetic calculator for explicit chat expressions."""
from __future__ import annotations

import ast
import operator
import re
from typing import Any, Dict, Optional

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_EXPRESSION_RE = re.compile(
    r"(?<![\w.])(?:\(\s*)?[-+]?\d(?:[\d,.\s]|[+\-*/()%])*[+\-*/%][\d,.\s()+\-*/%]*\d\)?"
)
_PERCENT_OF_RE = re.compile(
    r"(-?\d[\d,]*(?:\.\d+)?)\s*(?:%|percent|เปอร์เซ็นต์)"
    r"\s*(?:of|ของ)\s*(-?\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)
_AVERAGE_RE = re.compile(r"\b(?:average|mean)\b|ค่าเฉลี่ย", re.IGNORECASE)
_NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left = _eval(node.left)
        right = _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 12:
            raise ValueError("exponent is too large")
        return float(_OPS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return float(_OPS[type(node.op)](_eval(node.operand)))
    raise ValueError("unsupported calculation")


def calculate_from_question(question: str) -> Optional[Dict[str, Any]]:
    normalized_question = (question or "").replace("×", "*").replace("÷", "/")
    percent_match = _PERCENT_OF_RE.search(normalized_question)
    if percent_match:
        percent = float(percent_match.group(1).replace(",", ""))
        base = float(percent_match.group(2).replace(",", ""))
        result = percent * base / 100
        display_result: int | float = int(result) if result.is_integer() else round(result, 10)
        return {
            "engine": "safe_calculator",
            "expression": f"{percent}% of {base:g}",
            "result": display_result,
            "formatted": f"Verified calculator result: {percent:g}% of {base:g} = {display_result}",
        }
    if _AVERAGE_RE.search(normalized_question):
        values = [
            float(value.replace(",", ""))
            for value in _NUMBER_RE.findall(normalized_question)
        ]
        if values:
            result = sum(values) / len(values)
            display_result = int(result) if result.is_integer() else round(result, 10)
            expression = f"average({', '.join(f'{value:g}' for value in values)})"
            return {
                "engine": "safe_calculator",
                "expression": expression,
                "result": display_result,
                "formatted": f"Verified calculator result: {expression} = {display_result}",
            }
    match = _EXPRESSION_RE.search(normalized_question)
    if not match:
        return None
    expression = re.sub(r"\s+", "", match.group(0)).replace(",", "")
    if len(expression) > 120:
        return None
    try:
        parsed = ast.parse(expression, mode="eval")
        result = _eval(parsed)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
        return None
    display_result: int | float = int(result) if result.is_integer() else round(result, 10)
    return {
        "engine": "safe_calculator",
        "expression": expression,
        "result": display_result,
        "formatted": f"Verified calculator result: {expression} = {display_result}",
    }
