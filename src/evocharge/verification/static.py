"""Deterministic AST static verification for generated operators."""

from __future__ import annotations

import ast
import re
from typing import Literal

from pydantic import BaseModel, Field

from evocharge.operators.generated_api import (
    PLAN_FUNCTION_NAME,
    SCORE_FUNCTION_NAME,
)
from evocharge.operators.primitives import PRIMITIVE_IDS

FORBIDDEN_NAMES = {
    "eval",
    "exec",
    "compile",
    "open",
    "__import__",
    "getattr",
    "setattr",
    "delattr",
    "globals",
    "locals",
    "vars",
    "input",
    "breakpoint",
    "memoryview",
    "bytearray",
}
FORBIDDEN_MODULES = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "pathlib",
    "importlib",
    "ctypes",
    "multiprocessing",
    "threading",
    "http",
    "urllib",
    "requests",
    "pickle",
    "shutil",
    "tempfile",
}


class StaticLimits(BaseModel):
    max_ast_nodes: int = 400
    max_cyclomatic_complexity: int = 18
    max_loop_nesting: int = 3
    max_source_lines: int = 160
    allow_while: bool = False
    allow_recursion: bool = False


class StaticVerificationReport(BaseModel):
    accepted: bool
    operator_type: Literal["scoring", "plan_builder"] | None = None
    function_name: str | None = None
    used_primitives: list[str] = Field(default_factory=list)
    ast_nodes: int = 0
    cyclomatic_complexity: int = 0
    loop_nesting: int = 0
    source_lines: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _count_nodes(tree: ast.AST) -> int:
    return sum(1 for _ in ast.walk(tree))


def _cyclomatic(tree: ast.AST) -> int:
    score = 1
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With)):
            score += 1
        elif isinstance(node, ast.BoolOp):
            score += max(0, len(node.values) - 1)
        elif isinstance(node, ast.comprehension):
            score += 1
    return score


def _max_loop_nesting(tree: ast.AST) -> int:
    max_depth = 0

    def visit(node: ast.AST, depth: int) -> None:
        nonlocal max_depth
        if isinstance(node, (ast.For, ast.While)):
            depth += 1
            max_depth = max(max_depth, depth)
        for child in ast.iter_child_nodes(node):
            visit(child, depth)

    visit(tree, 0)
    return max_depth


def _extract_calls(func: ast.FunctionDef) -> list[str]:
    """Return bare Name call targets (not attribute methods like list.append)."""
    names: list[str] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.append(node.func.id)
    return names


def verify_source(
    source: str,
    *,
    expected_type: Literal["scoring", "plan_builder"],
    allowed_primitives: set[str] | None = None,
    limits: StaticLimits | None = None,
) -> StaticVerificationReport:
    limits = limits or StaticLimits()
    allowed = allowed_primitives or PRIMITIVE_IDS
    errors: list[str] = []
    warnings: list[str] = []
    lines = source.splitlines()
    if len(lines) > limits.max_source_lines:
        errors.append(f"too_many_lines:{len(lines)}")
    if re.search(r"[\u200b-\u200f\u202a-\u202e]", source):
        errors.append("hidden_unicode")
    if "```" in source:
        errors.append("markdown_fence")

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return StaticVerificationReport(
            accepted=False,
            errors=[f"syntax_error:{exc}"],
            source_lines=len(lines),
        )

    # Only one top-level function; no imports/classes/exec statements
    top_funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    other = [n for n in tree.body if not isinstance(n, ast.FunctionDef)]
    if other:
        errors.append("toplevel_non_function")
    if len(top_funcs) != 1:
        errors.append(f"expected_one_function:{len(top_funcs)}")
        return StaticVerificationReport(
            accepted=False,
            errors=errors,
            ast_nodes=_count_nodes(tree),
            source_lines=len(lines),
        )

    func = top_funcs[0]
    expected_name = (
        SCORE_FUNCTION_NAME if expected_type == "scoring" else PLAN_FUNCTION_NAME
    )
    if func.name != expected_name:
        errors.append(f"wrong_function_name:{func.name}")

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            errors.append("import_forbidden")
        if isinstance(node, ast.ClassDef):
            errors.append("class_forbidden")
        if isinstance(node, ast.Global):
            errors.append("global_forbidden")
        if isinstance(node, ast.Nonlocal):
            errors.append("nonlocal_forbidden")
        if isinstance(node, ast.While) and not limits.allow_while:
            errors.append("while_forbidden")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            errors.append(f"forbidden_name:{node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            errors.append(f"dunder_attr:{node.attr}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            # Block reflection-style attribute calls
            if node.func.attr in {"__getattribute__", "__getattr__", "__setattr__"}:
                errors.append(f"forbidden_attr_call:{node.func.attr}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_MODULES:
                errors.append(f"forbidden_call:{node.func.id}")

    if not limits.allow_recursion:
        for node in ast.walk(func):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == func.name:
                    errors.append("recursion_forbidden")

    nodes = _count_nodes(tree)
    complexity = _cyclomatic(tree)
    nesting = _max_loop_nesting(tree)
    if nodes > limits.max_ast_nodes:
        errors.append(f"ast_too_large:{nodes}")
    if complexity > limits.max_cyclomatic_complexity:
        errors.append(f"complexity_too_high:{complexity}")
    if nesting > limits.max_loop_nesting:
        errors.append(f"loop_nesting_too_deep:{nesting}")

    calls = _extract_calls(func)
    used_primitives = sorted({c for c in calls if c in PRIMITIVE_IDS})
    for c in calls:
        if c in PRIMITIVE_IDS and c not in allowed:
            errors.append(f"primitive_not_allowed:{c}")
        if c in FORBIDDEN_NAMES or c in FORBIDDEN_MODULES:
            errors.append(f"forbidden_call:{c}")
        # Disallow unknown calls except constructors/builtins of a tiny allowlist
        allow_misc = {
            "len",
            "min",
            "max",
            "sum",
            "abs",
            "float",
            "int",
            "str",
            "bool",
            "tuple",
            "list",
            "range",
            "enumerate",
            "zip",
            "sorted",
            "OperatorPlan",
            "PlanAction",
            "PrimitiveAction",
            "EntityCandidate",
            "EntityReference",
            "SelectionEvidence",
        }
        if c.startswith(
            (
                "plan_",
                "query_",
                "select_",
                "identify_",
                "enumerate_",
                "reconstruct_",
                "validate_",
                "evaluate_",
            )
        ):
            if c not in PRIMITIVE_IDS:
                errors.append(f"unknown_primitive:{c}")
            continue
        if c not in PRIMITIVE_IDS and c not in allow_misc and c != func.name:
            if c[0].islower():
                errors.append(f"unknown_call:{c}")

    # Signature checks (best-effort)
    args = [a.arg for a in func.args.args]
    if expected_type == "scoring" and args != ["context", "candidates"]:
        errors.append(f"bad_signature_args:{args}")
    if expected_type == "plan_builder" and args != ["state", "context", "rng"]:
        errors.append(f"bad_signature_args:{args}")
    if func.returns is None:
        warnings.append("missing_return_annotation")

    from evocharge.verification.hardcoded import detect_hardcoded_identities

    errors.extend(detect_hardcoded_identities(source))

    return StaticVerificationReport(
        accepted=not errors,
        operator_type=expected_type,
        function_name=func.name,
        used_primitives=used_primitives,
        ast_nodes=nodes,
        cyclomatic_complexity=complexity,
        loop_nesting=nesting,
        source_lines=len(lines),
        errors=sorted(set(errors)),
        warnings=sorted(set(warnings)),
    )


def extract_code_from_response(raw: str) -> str:
    """Pull a single python function from model output."""
    text = raw.strip()
    fence = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    # Keep from first def to end
    m = re.search(r"(def\s+(?:score_entities|build_operator_plan)\s*\(.*)", text, re.DOTALL)
    if m:
        text = m.group(1)
    return text.strip() + ("\n" if not text.endswith("\n") else "")
