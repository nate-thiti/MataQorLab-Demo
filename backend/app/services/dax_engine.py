"""Parser and fail-closed compiler for the documented MataQorLab DAX subset.

This is deliberately not a Power BI compatibility layer. Expressions are
tokenized into a typed AST and only known nodes/functions can reach DuckDB.
No source fragment is copied into SQL and no eval-style execution is used.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Optional


class DaxError(ValueError):
    """A deterministic, user-safe DAX validation error."""


SUPPORTED_FUNCTIONS = frozenset({
    "SUM", "AVERAGE", "MIN", "MAX", "COUNT", "COUNTROWS", "DISTINCTCOUNT",
    "DIVIDE", "IF", "COALESCE", "CALCULATE", "FILTER", "VALUES", "ALL",
    "REMOVEFILTERS", "DATEADD", "SAMEPERIODLASTYEAR", "DATESBETWEEN",
    "TOTALMTD", "TOTALQTD", "TOTALYTD", "SUMX", "AVERAGEX", "RELATED",
    "LOOKUPVALUE",
})

CONTEXT_FUNCTIONS = frozenset({
    "CALCULATE", "FILTER", "VALUES", "ALL", "REMOVEFILTERS", "DATEADD",
    "SAMEPERIODLASTYEAR", "DATESBETWEEN", "TOTALMTD", "TOTALQTD", "TOTALYTD",
    "RELATED", "LOOKUPVALUE",
})


@dataclass(frozen=True)
class DaxNode:
    kind: str


@dataclass(frozen=True)
class LiteralNode(DaxNode):
    value: Any


@dataclass(frozen=True)
class ColumnNode(DaxNode):
    column: str
    table: Optional[str] = None


@dataclass(frozen=True)
class UnaryNode(DaxNode):
    operator: str
    operand: DaxNode


@dataclass(frozen=True)
class BinaryNode(DaxNode):
    operator: str
    left: DaxNode
    right: DaxNode


@dataclass(frozen=True)
class FunctionNode(DaxNode):
    name: str
    arguments: tuple[DaxNode, ...]


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    position: int


_TOKEN_RE = re.compile(
    r"\s*(?:(?P<number>\d+(?:\.\d+)?)|(?P<string>\"(?:\"\"|[^\"])*\")|"
    r"(?P<column>\[[^\]\r\n]+\])|(?P<identifier>[A-Za-z_][A-Za-z0-9_ ]*)|"
    r"(?P<operator><>|<=|>=|&&|\|\||[+\-*/=<>(),]))"
)


def tokenize(expression: str) -> list[Token]:
    source = str(expression or "").strip()
    if not source or len(source) > 4_000:
        raise DaxError("DAX_EXPRESSION_REQUIRED_OR_TOO_LONG")
    tokens: list[Token] = []
    position = 0
    while position < len(source):
        match = _TOKEN_RE.match(source, position)
        if not match:
            raise DaxError(f"DAX_INVALID_TOKEN_AT_{position}")
        kind = next(name for name, value in match.groupdict().items() if value is not None)
        tokens.append(Token(kind, match.group(kind), position))
        position = match.end()
    tokens.append(Token("eof", "", len(source)))
    return tokens


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.index = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def consume(self, value: Optional[str] = None) -> Token:
        token = self.current
        if value is not None and token.value.upper() != value.upper():
            raise DaxError(f"DAX_EXPECTED_{value}_AT_{token.position}")
        self.index += 1
        return token

    def parse(self) -> DaxNode:
        node = self.expression(0)
        if self.current.kind != "eof":
            raise DaxError(f"DAX_UNEXPECTED_TOKEN_AT_{self.current.position}")
        return node

    def expression(self, minimum: int) -> DaxNode:
        token = self.current
        if token.value in {"+", "-"}:
            self.consume()
            left: DaxNode = UnaryNode("unary", token.value, self.expression(7))
        else:
            left = self.primary()
        precedence = {"||": 1, "&&": 2, "=": 3, "<>": 3, "<": 3, "<=": 3,
                      ">": 3, ">=": 3, "+": 4, "-": 4, "*": 5, "/": 5}
        while self.current.value in precedence and precedence[self.current.value] >= minimum:
            op = self.consume().value
            right = self.expression(precedence[op] + 1)
            left = BinaryNode("binary", op, left, right)
        return left

    def primary(self) -> DaxNode:
        token = self.current
        if token.kind == "number":
            self.consume()
            value: Any = float(token.value) if "." in token.value else int(token.value)
            return LiteralNode("literal", value)
        if token.kind == "string":
            self.consume()
            return LiteralNode("literal", token.value[1:-1].replace('""', '"'))
        if token.kind == "column":
            self.consume()
            return ColumnNode("column", token.value[1:-1].strip())
        if token.kind == "identifier":
            name = self.consume().value.strip()
            upper = name.upper()
            if self.current.kind == "column":
                column = self.consume().value[1:-1].strip()
                return ColumnNode("column", column, name)
            if self.current.value == "(":
                if upper not in SUPPORTED_FUNCTIONS:
                    raise DaxError(f"DAX_UNSUPPORTED_FUNCTION:{upper}")
                self.consume("(")
                args: list[DaxNode] = []
                if self.current.value != ")":
                    while True:
                        args.append(self.expression(0))
                        if self.current.value != ",":
                            break
                        self.consume(",")
                self.consume(")")
                return FunctionNode("function", upper, tuple(args))
            if upper in {"TRUE", "FALSE"}:
                return LiteralNode("literal", upper == "TRUE")
            if upper == "BLANK":
                return LiteralNode("literal", None)
            raise DaxError(f"DAX_BARE_IDENTIFIER_NOT_ALLOWED:{name}")
        if token.value == "(":
            self.consume("(")
            node = self.expression(0)
            self.consume(")")
            return node
        raise DaxError(f"DAX_EXPECTED_EXPRESSION_AT_{token.position}")


def parse_dax_expression(expression: str) -> DaxNode:
    return _Parser(tokenize(expression)).parse()


def _node_dict(node: DaxNode) -> dict[str, Any]:
    if isinstance(node, LiteralNode):
        return {"kind": "literal", "value": node.value}
    if isinstance(node, ColumnNode):
        return {"kind": "column", "table": node.table, "column": node.column}
    if isinstance(node, UnaryNode):
        return {"kind": "unary", "operator": node.operator, "operand": _node_dict(node.operand)}
    if isinstance(node, BinaryNode):
        return {"kind": "binary", "operator": node.operator,
                "left": _node_dict(node.left), "right": _node_dict(node.right)}
    if isinstance(node, FunctionNode):
        return {"kind": "function", "name": node.name,
                "arguments": [_node_dict(arg) for arg in node.arguments]}
    raise DaxError("DAX_UNKNOWN_AST_NODE")


def _walk(node: DaxNode) -> Iterable[DaxNode]:
    yield node
    if isinstance(node, UnaryNode):
        yield from _walk(node.operand)
    elif isinstance(node, BinaryNode):
        yield from _walk(node.left)
        yield from _walk(node.right)
    elif isinstance(node, FunctionNode):
        for argument in node.arguments:
            yield from _walk(argument)


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _literal_sql(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def _require_args(node: FunctionNode, minimum: int, maximum: Optional[int] = None) -> None:
    maximum = minimum if maximum is None else maximum
    if not minimum <= len(node.arguments) <= maximum:
        raise DaxError(f"DAX_INVALID_ARITY:{node.name}:{minimum}-{maximum}")


def compile_dax_expression(
    node: DaxNode,
    *,
    columns: Iterable[str],
    mode: Literal["measure", "calculated_column"] = "measure",
    governed_relationships: bool = False,
) -> str:
    available = set(columns)

    def compile_node(item: DaxNode, *, row_context: bool = False) -> str:
        if isinstance(item, LiteralNode):
            return _literal_sql(item.value)
        if isinstance(item, ColumnNode):
            if item.column not in available:
                raise DaxError(f"DAX_UNKNOWN_COLUMN:{item.column}")
            return _quote_identifier(item.column)
        if isinstance(item, UnaryNode):
            return f"({item.operator}{compile_node(item.operand, row_context=row_context)})"
        if isinstance(item, BinaryNode):
            op = {"=": "=", "<>": "!=", "&&": "AND", "||": "OR"}.get(item.operator, item.operator)
            return f"({compile_node(item.left, row_context=row_context)} {op} {compile_node(item.right, row_context=row_context)})"
        if not isinstance(item, FunctionNode):
            raise DaxError("DAX_UNKNOWN_AST_NODE")
        name = item.name
        if name in {"RELATED", "LOOKUPVALUE"} and not governed_relationships:
            raise DaxError("DAX_GOVERNED_RELATIONSHIP_REQUIRED")
        if name in CONTEXT_FUNCTIONS:
            raise DaxError(f"DAX_QUERY_CONTEXT_REQUIRED:{name}")
        if name in {"SUM", "AVERAGE", "MIN", "MAX", "COUNT", "DISTINCTCOUNT"}:
            if mode == "calculated_column" and not row_context:
                raise DaxError(f"DAX_AGGREGATE_NOT_ALLOWED_IN_CALCULATED_COLUMN:{name}")
            _require_args(item, 1)
            expression = compile_node(item.arguments[0], row_context=row_context)
            sql_name = {"AVERAGE": "AVG", "DISTINCTCOUNT": "COUNT(DISTINCT"}.get(name, name)
            return f"COUNT(DISTINCT {expression})" if name == "DISTINCTCOUNT" else f"{sql_name}({expression})"
        if name == "COUNTROWS":
            _require_args(item, 0)
            return "COUNT(*)"
        if name in {"SUMX", "AVERAGEX"}:
            _require_args(item, 2)
            expression = compile_node(item.arguments[1], row_context=True)
            return f"{'SUM' if name == 'SUMX' else 'AVG'}({expression})"
        if name == "DIVIDE":
            _require_args(item, 2, 3)
            numerator = compile_node(item.arguments[0], row_context=row_context)
            denominator = compile_node(item.arguments[1], row_context=row_context)
            alternate = compile_node(item.arguments[2], row_context=row_context) if len(item.arguments) == 3 else "NULL"
            return f"(CASE WHEN ({denominator}) IS NULL OR ({denominator}) = 0 THEN {alternate} ELSE ({numerator}) / ({denominator}) END)"
        if name == "IF":
            _require_args(item, 2, 3)
            condition = compile_node(item.arguments[0], row_context=row_context)
            yes = compile_node(item.arguments[1], row_context=row_context)
            no = compile_node(item.arguments[2], row_context=row_context) if len(item.arguments) == 3 else "NULL"
            return f"(CASE WHEN {condition} THEN {yes} ELSE {no} END)"
        if name == "COALESCE":
            _require_args(item, 2, 20)
            return "COALESCE(" + ", ".join(compile_node(arg, row_context=row_context) for arg in item.arguments) + ")"
        raise DaxError(f"DAX_UNSUPPORTED_EXECUTION_FUNCTION:{name}")

    return compile_node(node)


def validate_dax_expression(
    expression: str,
    *,
    columns: Iterable[str],
    mode: Literal["measure", "calculated_column"] = "measure",
    governed_relationships: bool = False,
) -> dict[str, Any]:
    node = parse_dax_expression(expression)
    ast = _node_dict(node)
    dependencies = sorted({item.column for item in _walk(node) if isinstance(item, ColumnNode)})
    context_functions = sorted({item.name for item in _walk(node) if isinstance(item, FunctionNode) and item.name in CONTEXT_FUNCTIONS})
    sql: Optional[str] = None
    executable = True
    execution_error: Optional[str] = None
    try:
        sql = compile_dax_expression(
            node, columns=columns, mode=mode,
            governed_relationships=governed_relationships,
        )
    except DaxError as exc:
        executable = False
        execution_error = str(exc)
    normalized = json.dumps(ast, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "valid": True,
        "executable": executable,
        "language": "dax_subset_v1",
        "mode": mode,
        "normalized_ast": ast,
        "dependencies": dependencies,
        "context_functions": context_functions,
        "compiled_expression": sql,
        "execution_error": execution_error,
        "formula_hash": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "output_type": "number" if mode == "measure" else "inferred",
        "version": 1,
    }

