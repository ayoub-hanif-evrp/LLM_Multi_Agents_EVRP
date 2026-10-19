"""Bounded arithmetic interpreter for scoring components.

Generated functions are never ``exec``'d in the controller. Only a closed set of
AST nodes is evaluated, with a step budget.
"""
from __future__ import annotations

import ast
from collections.abc import Callable
from typing import Any

_ALLOWED_FUNCS: dict[str, Callable[..., float]] = {
    "abs": abs,
    "min": min,
    "max": max,
    "float": float,
    "int": int,
    "round": round,
}
_MAX_STEPS = 200


class UnsafeComponent(ValueError):
    """Raised when component source is outside the arithmetic subset."""


def _eval(node: ast.AST, env: dict[str, float], steps: list[int]) -> float:
    steps[0] += 1
    if steps[0] > _MAX_STEPS:
        raise UnsafeComponent("step budget exceeded")
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise UnsafeComponent(f"unknown name {node.id}")
        return float(env[node.id])
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval(node.operand, env, steps)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left = _eval(node.left, env, steps)
        right = _eval(node.right, env, steps)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise UnsafeComponent("division by zero")
        return left / right
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        left = _eval(node.left, env, steps)
        right = _eval(node.comparators[0], env, steps)
        op = node.ops[0]
        ok = False
        if isinstance(op, ast.Lt):
            ok = left < right
        elif isinstance(op, ast.LtE):
            ok = left <= right
        elif isinstance(op, ast.Gt):
            ok = left > right
        elif isinstance(op, ast.GtE):
            ok = left >= right
        elif isinstance(op, ast.Eq):
            ok = left == right
        elif isinstance(op, ast.NotEq):
            ok = left != right
        else:
            raise UnsafeComponent("comparison not allowed")
        return 1.0 if ok else 0.0
    if isinstance(node, ast.IfExp):
        cond = _eval(node.test, env, steps)
        return _eval(node.body if cond else node.orelse, env, steps)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCS:
        args = [_eval(arg, env, steps) for arg in node.args]
        return float(_ALLOWED_FUNCS[node.func.id](*args))
    raise UnsafeComponent(f"disallowed syntax: {type(node).__name__}")


def compile_component(kind: str, source: str) -> Any:
    """Return a pure callable bound to the named function's arguments."""
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        raise UnsafeComponent("module-level statements are not allowed")
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == kind]
    if len(funcs) != 1:
        raise UnsafeComponent(f"expected one function {kind}")
    func = funcs[0]
    if func.args.vararg or func.args.kwarg or func.args.kwonlyargs:
        raise UnsafeComponent("variadic arguments not allowed")
    params = [a.arg for a in func.args.args]
    body = [stmt for stmt in func.body if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Constant)]
    returns = [stmt for stmt in body if isinstance(stmt, ast.Return)]
    if len(returns) != 1 or len(body) != 1:
        raise UnsafeComponent("function body must be a single return")
    expr = returns[0].value
    if expr is None:
        raise UnsafeComponent("empty return")

    def call(*args: float) -> float:
        if len(args) != len(params):
            raise TypeError(f"{kind} expected {len(params)} args, got {len(args)}")
        env = {name: float(value) for name, value in zip(params, args, strict=True)}
        value = _eval(expr, env, [0])
        if value != value or value in (float("inf"), float("-inf")):
            raise UnsafeComponent("non-finite result")
        return float(value)

    call.parameter_names = tuple(params)  # type: ignore[attr-defined]
    return call
