"""Restricted scoring language. Generated text cannot import, read files, or call the host."""

from __future__ import annotations

import ast
import math
from collections.abc import Mapping, Sequence

_MAX_SOURCE_CHARS = 500
_MAX_NODES = 64
_FUNCTIONS = frozenset({"min", "max", "abs"})
FORBIDDEN_FEATURE_NAMES = frozenset(
    {
        "instance_id",
        "instance_name",
        "filename",
        "family",
        "seed",
        "future_objective",
        "benchmark",
    }
)
EXPENSIVE_CONTEXT_FEATURES = frozenset({"battery_slack", "time_window_slack"})


class PolicyError(ValueError):
    """The expression is not a legal bounded policy."""


def normalize_expression(source: str) -> str:
    """Map boolean literals to numeric constants. Everything else is left unchanged."""
    if not isinstance(source, str):
        raise PolicyError("empty policy")
    text = source.strip()
    if not text:
        raise PolicyError("empty policy")
    lowered = text.lower()
    if lowered == "true":
        return "1"
    if lowered == "false":
        return "0"
    return text


def referenced_features(source: str) -> set[str]:
    """Feature names referenced by a legal expression."""
    tree = _parse_policy(normalize_expression(source))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in _FUNCTIONS:
            names.add(node.id)
    return names


def validate_expression(source: str, allowed_features: set[str] | frozenset[str]) -> str:
    """Reject illegal syntax or unknown features before the solver runs. Returns the normalized source."""
    normalized = normalize_expression(source)
    tree = _parse_policy(normalized)
    for name in referenced_features(normalized):
        if name in FORBIDDEN_FEATURE_NAMES:
            raise PolicyError(f"forbidden feature {name}")
        if name not in allowed_features:
            raise PolicyError(f"unknown feature {name}")
    # Constant-only expressions are legal (e.g. normalized ``1``).
    _ = tree
    return normalized


def needs_expensive_context(*expressions: str | None) -> bool:
    """True when any expression needs battery or time-window slack from route simulation."""
    for expression in expressions:
        if not expression:
            continue
        try:
            names = referenced_features(expression)
        except PolicyError:
            continue
        if names & EXPENSIVE_CONTEXT_FEATURES:
            return True
    return False


def evaluate_policy(source: str, features: Mapping[str, float]) -> float:
    """Evaluate one expression. The result is a finite float."""
    normalized = normalize_expression(source)
    if any(name in features for name in FORBIDDEN_FEATURE_NAMES):
        raise PolicyError("forbidden feature supplied")
    tree = _parse_policy(normalized)
    value = _eval(tree.body, features)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PolicyError("policy did not return a number")
    number = float(value)
    if not math.isfinite(number):
        raise PolicyError("policy returned a non-finite number")
    return number


def _parse_policy(source: str) -> ast.Expression:
    if len(source) > _MAX_SOURCE_CHARS:
        raise PolicyError("policy exceeds the length bound")
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise PolicyError("policy syntax rejected") from exc
    if not isinstance(tree, ast.Expression):
        raise PolicyError("policy syntax rejected")
    if sum(1 for _ in ast.walk(tree)) > _MAX_NODES:
        raise PolicyError("policy exceeds the node bound")
    return tree


def choose_minimum(source: str, rows: Sequence[Mapping[str, float]]) -> int:
    """Return the row index with the smallest finite score. Ties keep the earlier row."""
    if not rows:
        raise PolicyError("no candidate rows")
    scores = [evaluate_policy(source, row) for row in rows]
    return min(range(len(scores)), key=lambda index: (scores[index], index))


def _eval(node: ast.AST, features: Mapping[str, float]) -> float | bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        if node.id in FORBIDDEN_FEATURE_NAMES:
            raise PolicyError(f"forbidden feature {node.id}")
        if node.id not in features:
            raise PolicyError(f"unknown feature {node.id}")
        return float(features[node.id])
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
        value = float(_eval(node.operand, features))
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Sub | ast.Mult | ast.Div):
        left = float(_eval(node.left, features))
        right = float(_eval(node.right, features))
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0.0:
            raise PolicyError("division by zero")
        return left / right
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        left = float(_eval(node.left, features))
        right = float(_eval(node.comparators[0], features))
        op = node.ops[0]
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And | ast.Or):
        values = [_truth(_eval(item, features)) for item in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.IfExp):
        chosen = node.body if _truth(_eval(node.test, features)) else node.orelse
        return _eval(chosen, features)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS:
        if node.keywords:
            raise PolicyError("keyword arguments are rejected")
        arguments = [float(_eval(item, features)) for item in node.args]
        if node.func.id == "abs":
            if len(arguments) != 1:
                raise PolicyError("abs expects one argument")
            return abs(arguments[0])
        if len(arguments) < 1:
            raise PolicyError(f"{node.func.id} expects an argument")
        if node.func.id == "min":
            return min(arguments)
        return max(arguments)
    raise PolicyError("unsupported policy syntax")


def _truth(value: float | bool) -> bool:
    if isinstance(value, bool):
        return value
    return float(value) != 0.0
