"""AST-based ADD / REPLACE / REMOVE of module-level functions in solver.py."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from evrptw_autolab.slm_evo.types import PatchOp, PatchProposal


@dataclass
class ApplyResult:
    ok: bool
    source: str = ""
    error: str = ""


def _top_level_funcs(tree: ast.AST) -> dict[str, ast.FunctionDef]:
    if not isinstance(tree, ast.Module):
        return {}
    out: dict[str, ast.FunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out[node.name] = node
    return out


def _extract_def_name(code: str) -> str | None:
    text = (code or "").strip()
    if not text:
        return None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        m = re.search(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text, re.M)
        return m.group(1) if m else None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    return None


def _normalize_code(code: str) -> str:
    text = (code or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _segment_source(source: str) -> tuple[str, list[tuple[str, str]], str]:
    """Split into (preamble, [(name, def_block), ...], trailing).

    Uses line-based AST offsets so we can rewrite function bodies safely.
    """
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    funcs = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            start = node.lineno - 1
            end = (node.end_lineno or node.lineno) - 1
            block = "".join(lines[start : end + 1])
            if not block.endswith("\n"):
                block += "\n"
            funcs.append((node.name, start, end, block))
    if not funcs:
        return source if source.endswith("\n") else source + "\n", [], ""

    preamble = "".join(lines[: funcs[0][1]])
    ordered: list[tuple[str, str]] = [(name, block) for name, _, _, block in funcs]
    last_end = funcs[-1][2]
    trailing = "".join(lines[last_end + 1 :])
    return preamble, ordered, trailing


def _rebuild(preamble: str, funcs: list[tuple[str, str]], trailing: str) -> str:
    parts = [preamble]
    for _, block in funcs:
        b = block if block.endswith("\n") else block + "\n"
        if parts and parts[-1] and not parts[-1].endswith("\n"):
            parts.append("\n")
        parts.append(b)
        if not b.endswith("\n\n"):
            parts.append("\n")
    if trailing:
        parts.append(trailing if trailing.endswith("\n") else trailing + "\n")
    text = "".join(parts)
    if not text.endswith("\n"):
        text += "\n"
    return text


def apply_ops(source: str, ops: list[PatchOp]) -> ApplyResult:
    """Apply a sequence of ADD/REPLACE/REMOVE ops to module-level functions."""
    if not ops:
        return ApplyResult(False, error="empty ops")
    try:
        ast.parse(source)
    except SyntaxError as err:
        return ApplyResult(False, error=f"parent syntax: {err}")

    # Validate ops against planned end state before mutating.
    names_now = set(_top_level_funcs(ast.parse(source)))
    planned = set(names_now)
    for op in ops:
        action = str(op.action).upper()
        symbol = (op.symbol or "").strip()
        if not symbol:
            return ApplyResult(False, error="missing symbol")
        if action == "ADD":
            code = _normalize_code(op.code)
            def_name = _extract_def_name(code)
            if def_name is None:
                return ApplyResult(False, error=f"ADD code has no def: {symbol}")
            if def_name != symbol:
                return ApplyResult(
                    False, error=f"ADD symbol mismatch: op={symbol} code={def_name}"
                )
            if symbol in planned:
                return ApplyResult(False, error=f"ADD collision: {symbol}")
            try:
                ast.parse(code)
            except SyntaxError as err:
                return ApplyResult(False, error=f"ADD syntax {symbol}: {err}")
            planned.add(symbol)
        elif action == "REPLACE":
            code = _normalize_code(op.code)
            def_name = _extract_def_name(code)
            if def_name is None:
                return ApplyResult(False, error=f"REPLACE code has no def: {symbol}")
            if def_name != symbol:
                return ApplyResult(
                    False, error=f"REPLACE symbol mismatch: op={symbol} code={def_name}"
                )
            if symbol not in planned:
                return ApplyResult(False, error=f"REPLACE missing: {symbol}")
            try:
                ast.parse(code)
            except SyntaxError as err:
                return ApplyResult(False, error=f"REPLACE syntax {symbol}: {err}")
        elif action == "REMOVE":
            if symbol not in planned:
                return ApplyResult(False, error=f"REMOVE missing: {symbol}")
            planned.remove(symbol)
        else:
            return ApplyResult(False, error=f"unknown action: {action}")

    if "solve" not in planned:
        return ApplyResult(False, error="ops would remove def solve without replacement")

    preamble, funcs, trailing = _segment_source(source)
    by_name = {name: block for name, block in funcs}
    order = [name for name, _ in funcs]

    for op in ops:
        action = str(op.action).upper()
        symbol = op.symbol.strip()
        if action == "ADD":
            code = _normalize_code(op.code)
            if not code.endswith("\n"):
                code += "\n"
            by_name[symbol] = code
            order.append(symbol)
        elif action == "REPLACE":
            code = _normalize_code(op.code)
            if not code.endswith("\n"):
                code += "\n"
            by_name[symbol] = code
        elif action == "REMOVE":
            by_name.pop(symbol, None)
            order = [n for n in order if n != symbol]

    new_funcs = [(n, by_name[n]) for n in order if n in by_name]
    # Keep any newly added not already ordered (shouldn't happen)
    for n, block in by_name.items():
        if n not in {x[0] for x in new_funcs}:
            new_funcs.append((n, block))

    out = _rebuild(preamble, new_funcs, trailing)
    try:
        tree = ast.parse(out)
        compile(out, "<solver.py>", "exec")
    except SyntaxError as err:
        return ApplyResult(False, error=f"result syntax: {err}")
    if "solve" not in _top_level_funcs(tree):
        return ApplyResult(False, error="result missing def solve")
    return ApplyResult(True, source=out)


def apply_proposal(source: str, proposal: PatchProposal) -> ApplyResult:
    return apply_ops(source, proposal.ops)


def parse_proposal_json(data: dict, *, role: str = "", seed: int | None = None) -> PatchProposal:
    hypothesis = str(data.get("hypothesis") or "")[:800]
    raw_ops = data.get("ops") or []
    if not isinstance(raw_ops, list) or not raw_ops:
        raise ValueError("proposal needs non-empty ops list")
    ops: list[PatchOp] = []
    for item in raw_ops:
        if not isinstance(item, dict):
            raise ValueError("op must be object")
        action = str(item.get("action") or "").upper()
        if action not in {"ADD", "REPLACE", "REMOVE"}:
            raise ValueError(f"bad action: {action}")
        symbol = str(item.get("symbol") or "").strip()
        code = str(item.get("code") or "")
        ops.append(PatchOp(action=action, symbol=symbol, code=code))  # type: ignore[arg-type]
    return PatchProposal(hypothesis=hypothesis, ops=ops, role=role, seed=seed)
