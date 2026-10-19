"""Turn a validated arithmetic expression into a trusted scoring function.

The LLM is asked for an expression, not a free-form function. The controller
wraps that expression in a fixed signature. Legacy full-function replies are
normalized (including doubly escaped newlines) and still must pass the
bounded interpreter.
"""
from __future__ import annotations

import ast

from evrptw_autolab.components.interfaces import DEFAULT_SOURCES, ComponentKind
from evrptw_autolab.components.interpret import UnsafeComponent, _eval
from evrptw_autolab.problem.v2.features import FEATURE_SCHEMA_V3, feature_schema_prompt

ARGUMENT_NAMES: dict[ComponentKind, tuple[str, ...]] = {
    "insertion_score": (
        "delta_distance",
        "due_time",
        "ready_time",
        "demand",
        "capacity_slack",
    ),
    "station_score": ("detour", "battery_arrival", "station_rate"),
    "removal_priority": ("due_time", "route_distance_share", "rng_value"),
}

ARGUMENT_NAMES_V3: dict[ComponentKind, tuple[str, ...]] = {
    "insertion_score": ARGUMENT_NAMES["insertion_score"]
    + ("vehicle_fixed_cost", "marginal_energy", "new_route_fixed_cost"),
    "station_score": ARGUMENT_NAMES["station_score"] + ("charge_time",),
    "removal_priority": ARGUMENT_NAMES["removal_priority"],
}

EXPRESSION_EXAMPLES: dict[ComponentKind, str] = {
    "insertion_score": "delta_distance + 0.01 * due_time",
    "station_score": "detour + 0.1 * station_rate",
    "removal_priority": "due_time + 10.0 * route_distance_share + 0.01 * rng_value",
}


def normalize_llm_source(text: str) -> str:
    """Decode literal ``\\n`` sequences left by double-escaped JSON strings.

    Only rewrites escape sequences. Does not eval the source.
    """
    raw = str(text or "").strip()
    if "\\n" not in raw and "\\t" not in raw:
        return raw
    # Real newlines already present and no leftover escapes: leave it.
    if raw.count("\n") >= 1 and "\\n" not in raw:
        return raw
    return raw.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "    ")


def _check_expression(node: ast.AST, allowed: set[str], depth: int = 0) -> None:
    if depth > 12:
        raise UnsafeComponent("expression too deep")
    # Reuse the interpreter's allow-list by evaluating against dummy zeros after a walk
    # that rejects names outside the signature. Structural checks happen in _eval.
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id not in allowed and child.id not in {
            "abs",
            "min",
            "max",
            "float",
            "int",
            "round",
        }:
            raise UnsafeComponent(f"unknown name {child.id}")
        if isinstance(child, (ast.Import, ast.ImportFrom, ast.Attribute, ast.Subscript, ast.Lambda)):
            raise UnsafeComponent(f"disallowed syntax: {type(child).__name__}")
    # Probe with zeros so disallowed operators fail before wrapping.
    env = {name: 1.0 for name in allowed}
    _eval(node, env, [0])


def default_sources(schema: str | None = None) -> dict[ComponentKind, str]:
    """v3 uses the same formulas as v1 and adds the new parameters unused."""
    if schema != FEATURE_SCHEMA_V3:
        return {kind: DEFAULT_SOURCES[kind] for kind in DEFAULT_SOURCES}
    bodies = {
        "insertion_score": (
            "delta_distance + (0.0 if due_time >= 1000000.0 else "
            "(0.01 * due_time + 1.0 / max(due_time - ready_time, 1.0))) + "
            "(0.0 if capacity_slack >= demand else 1000000.0)"
        ),
        "station_score": "detour + 0.1 * station_rate + (0.0 if battery_arrival > 0.0 else 1000.0)",
        "removal_priority": (
            "(0.0 if due_time >= 1000000.0 else due_time) + 10.0 * route_distance_share + 0.01 * rng_value"
        ),
    }
    return {kind: wrap_expression(kind, body, FEATURE_SCHEMA_V3) for kind, body in bodies.items()}


def argument_names(kind: ComponentKind, schema: str | None = None) -> tuple[str, ...]:
    """v3 names are a superset. A v1 expression cannot see the added features."""
    if schema == FEATURE_SCHEMA_V3:
        return ARGUMENT_NAMES_V3[kind]
    return ARGUMENT_NAMES[kind]


def wrap_expression(kind: ComponentKind, expression: str, schema: str | None = None) -> str:
    """Build the only function body the interpreter accepts: one return."""
    text = str(expression or "").strip()
    if not text or "\n" in text or ";" in text:
        raise UnsafeComponent("expression must be a single arithmetic line")
    if text.startswith("def ") or "import " in text:
        raise UnsafeComponent("return an expression, not a function or import")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as error:
        raise UnsafeComponent(str(error)) from error
    names = argument_names(kind, schema)
    allowed = set(names)
    _check_expression(tree.body, allowed)
    params = ", ".join(f"{name}: float" for name in names)
    return f"def {kind}({params}) -> float:\n    return {text}\n"


def materialize_component(
    kind: ComponentKind,
    payload: dict[str, object],
    schema: str | None = None,
) -> tuple[str, str]:
    """Return (source, status). Status starting with ``fallback`` means unused LLM code."""
    expression = str(payload.get("expression") or "").strip()
    if expression:
        try:
            return wrap_expression(kind, expression, schema), "expression_wrapped"
        except (UnsafeComponent, SyntaxError, ValueError) as error:
            return "", f"expression_rejected:{error}"
    code = normalize_llm_source(str(payload.get("code") or ""))
    if f"def {kind}" in code:
        return code, "normalized_function"
    return "", "fallback_missing_def"


def repair_prompt(kind: ComponentKind, error: str) -> str:
    names = ", ".join(ARGUMENT_NAMES[kind])
    example = EXPRESSION_EXAMPLES[kind]
    return (
        f"The previous {kind} was rejected: {error}\n"
        "Accepted language: ONE arithmetic expression. No def, no if, no assignments, no imports.\n"
        f"Allowed names: {names}. Allowed calls: abs min max float int round.\n"
        f"Example expression: {example}\n"
        + (feature_schema_prompt() + "\n" if kind == "station_score" else "")
        + 'Return ONLY JSON: {"component":"'
        + kind
        + '","expression":"...","rationale":"...","mechanism":"expression"}'
    )
