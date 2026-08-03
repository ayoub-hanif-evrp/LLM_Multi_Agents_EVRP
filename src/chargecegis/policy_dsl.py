"""Safe, typed JSON AST for ChargeCEGIS move-priority policies."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Literal, TypeAlias

from .features import FEATURE_NAMES

Policy: TypeAlias = dict[str, Any]
ExprType = Literal["NUMBER", "BOOLEAN"]

FEATURE_TYPES: dict[str, ExprType] = {name: "NUMBER" for name in FEATURE_NAMES}

MAX_NODES, MAX_DEPTH, MAX_CONDITIONALS, MAX_CONSTANT_ABS = 45, 6, 4, 5.0
REQUIRE_FEATURE_USE = True

# Structural argument shapes (used for parsing/complexity, independent of type rules).
_NARY = {"add", "mul", "min", "max", "and", "or"}
_BINARY = {"sub", "safe_div", "lt", "le", "gt", "ge"}
_UNARY = {"abs", "neg", "not"}
_OPS = _NARY | _BINARY | _UNARY | {"if"}

# Type rules: which operations require/produce NUMBER vs BOOLEAN.
_ARITH_NARY = {"add", "mul", "min", "max"}
_LOGIC_NARY = {"and", "or"}
_ARITH_BINARY = {"sub", "safe_div"}
_CMP_BINARY = {"lt", "le", "gt", "ge"}
_ARITH_UNARY = {"abs", "neg"}
_LOGIC_UNARY = {"not"}


def parse_policy(obj: Any) -> Policy:
    """Parse only JSON-like AST values; validation rejects every other construct."""
    if isinstance(obj, str):
        obj = json.loads(obj)
    if not isinstance(obj, dict):
        raise ValueError("policy must be a JSON object")
    validate_policy(obj)
    return obj


def complexity(ast: Policy) -> dict[str, int]:
    """Return structural metrics without evaluating untrusted policy content."""
    def walk(node: Any, depth: int) -> tuple[int, int, int, bool]:
        if not isinstance(node, dict):
            raise ValueError("AST node must be an object")
        if set(node) == {"feature"}:
            return 1, depth, 0, True
        if set(node) == {"const"}:
            return 1, depth, 0, False
        op = node.get("op")
        children = (
            [*node.get("args", [])] if op in _NARY else
            [node.get("left"), node.get("right")] if op in _BINARY else
            [node.get("arg")] if op in _UNARY else
            [node.get("condition"), node.get("then"), node.get("else")] if op == "if" else []
        )
        values = [walk(child, depth + 1) for child in children]
        return (1 + sum(v[0] for v in values), max([depth, *(v[1] for v in values)]),
                (1 if op == "if" else 0) + sum(v[2] for v in values), any(v[3] for v in values))
    nodes, depth, conditionals, features = walk(ast, 1)
    return {"nodes": nodes, "depth": depth, "conditionals": conditionals, "feature_uses": int(features)}


def _check_types(node: Any) -> ExprType:
    """Validate structure, reject unknown ops/features, and infer NUMBER/BOOLEAN types."""
    if not isinstance(node, dict):
        raise ValueError("AST node must be an object")
    keys = set(node)
    if keys == {"feature"}:
        name = node["feature"]
        if not isinstance(name, str) or not name:
            raise ValueError("feature must be a nonempty string")
        if name not in FEATURE_TYPES:
            raise ValueError(f"unknown feature: {name!r}")
        return FEATURE_TYPES[name]
    if keys == {"const"}:
        value = node["const"]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError("constant must be finite number")
        if abs(float(value)) > MAX_CONSTANT_ABS:
            raise ValueError("constant exceeds bound")
        return "NUMBER"
    op = node.get("op")
    if op not in _OPS:
        raise ValueError(f"unknown or forbidden operation: {op!r}")
    expected = {"op", "args"} if op in _NARY else (
        {"op", "left", "right"} if op in _BINARY else
        {"op", "arg"} if op in _UNARY else {"op", "condition", "then", "else"})
    if keys != expected:
        raise ValueError(f"invalid fields for {op}")
    if op in _NARY:
        children = node["args"]
        if not isinstance(children, list) or len(children) < 2:
            raise ValueError(f"{op} needs at least two args")
        types = [_check_types(child) for child in children]
        want: ExprType = "NUMBER" if op in _ARITH_NARY else "BOOLEAN"
        if any(t != want for t in types):
            raise ValueError(f"{op} requires {want} operands")
        return want
    if op in _BINARY:
        left, right = _check_types(node["left"]), _check_types(node["right"])
        if left != "NUMBER" or right != "NUMBER":
            raise ValueError(f"{op} requires NUMBER operands")
        return "NUMBER" if op in _ARITH_BINARY else "BOOLEAN"
    if op in _UNARY:
        arg_type = _check_types(node["arg"])
        if op in _ARITH_UNARY:
            if arg_type != "NUMBER":
                raise ValueError(f"{op} requires a NUMBER operand")
            return "NUMBER"
        if arg_type != "BOOLEAN":
            raise ValueError("not requires a BOOLEAN operand")
        return "BOOLEAN"
    # op == "if"
    condition_type = _check_types(node["condition"])
    then_type = _check_types(node["then"])
    else_type = _check_types(node["else"])
    if condition_type != "BOOLEAN":
        raise ValueError("if condition must be BOOLEAN")
    if then_type != "NUMBER" or else_type != "NUMBER":
        raise ValueError("if branches must be NUMBER")
    return "NUMBER"


def validate_policy(ast: Policy) -> None:
    """Reject malformed ASTs, unknown ops/features, type errors, and complexity violations."""
    root_type = _check_types(ast)
    if root_type != "NUMBER":
        raise ValueError("policy root must evaluate to NUMBER")
    metrics = complexity(ast)
    if metrics["nodes"] > MAX_NODES or metrics["depth"] > MAX_DEPTH:
        raise ValueError("policy complexity limit exceeded")
    if metrics["conditionals"] > MAX_CONDITIONALS:
        raise ValueError("too many conditionals")
    if REQUIRE_FEATURE_USE and not metrics["feature_uses"]:
        raise ValueError("policy does not use a feature")


def evaluate(ast: Policy, features: dict[str, float]) -> float:
    """Evaluate a validated, type-checked AST. Missing features deliberately evaluate to zero."""
    validate_policy(ast)
    def ev(node: Policy) -> float | bool:
        if "feature" in node:
            value = features.get(node["feature"], 0.0)
            return float(value) if math.isfinite(float(value)) else 0.0
        if "const" in node:
            return float(node["const"])
        op = node["op"]
        if op == "if":
            return ev(node["then"]) if bool(ev(node["condition"])) else ev(node["else"])
        if op in _NARY:
            values = [ev(a) for a in node["args"]]
            if op == "add": return float(sum(values))
            if op == "mul":
                result = 1.0
                for value in values: result *= float(value)
                return result
            if op == "min": return min(float(v) for v in values)
            if op == "max": return max(float(v) for v in values)
            return all(bool(v) for v in values) if op == "and" else any(bool(v) for v in values)
        if op in _UNARY:
            value = ev(node["arg"])
            return abs(float(value)) if op == "abs" else -float(value) if op == "neg" else not bool(value)
        left, right = ev(node["left"]), ev(node["right"])
        if op == "sub": return float(left) - float(right)
        if op == "safe_div": return 0.0 if abs(float(right)) < 1e-12 else float(left) / float(right)
        return {"lt": left < right, "le": left <= right, "gt": left > right, "ge": left >= right}[op]
    result = ev(ast)
    return float(result) if math.isfinite(float(result)) else 0.0


def policy_hash(ast: Policy) -> str:
    validate_policy(ast)
    return hashlib.sha256(json.dumps(ast, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
