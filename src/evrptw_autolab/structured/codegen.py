"""Generate / patch one structured function at a time via LLM."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from evrptw_autolab.agents.base import extract_json, extract_python_source
from evrptw_autolab.evolution.patch_apply import apply_proposal, proposal_from_raw_function
from evrptw_autolab.evolution.types import PatchOp, PatchProposal
from evrptw_autolab.llm.usage import BudgetExhausted, UsageLog
from evrptw_autolab.problem.micro import (
    micro_g1_one_customer,
    micro_g2_needs_charge,
    micro_g3_two_customers,
)
from evrptw_autolab.structured.signatures import (
    DEFAULT_IMPORTS,
    REQUIRED_FUNCTIONS,
    assemble_solver_source,
    stub_solver_source,
)
from evrptw_autolab.structured.spec import FormalSpec

ROOT = Path(__file__).resolve().parents[3]
PROMPTS = ROOT / "prompts" / "structured"

FUNCTION_ROLES = {
    "construct": "construct",
    "repair": "repair",
    "improve": "improve",
    "solve": "solve",
    "mutate": "mutate",
    "crossover": "crossover",
    "architect": "architect",
    "error_analyst": "error_analyst",
    "repair_coder": "repair_coder",
    "judge": "judge",
}


def load_prompt(name: str) -> str:
    path = PROMPTS / name
    if not path.exists():
        path = PROMPTS / f"{name}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _record_usage(backend: Any, usage_log: UsageLog | None, *, role: str, model: str) -> None:
    if usage_log is None:
        return
    from evrptw_autolab.llm.usage import LLMUsage

    last = getattr(backend, "last_usage", None)
    if last is not None:
        last.role = role
        if not getattr(last, "model_tag", None):
            last.model_tag = model
        usage_log.record(last)
        return
    usage_log.record(
        LLMUsage(
            model_id=model,
            provider=type(backend).__name__,
            role=role,
            latency_s=0.0,
            model_tag=model,
        )
    )


def llm_complete(
    backend: Any,
    *,
    prompt: str,
    role: str,
    model: str,
    temperature: float = 0.4,
    json_mode: bool = True,
    usage_log: UsageLog | None = None,
    max_calls: int | None = None,
    token_ceiling: int | None = None,
    reasoning_effort: str | None = None,
) -> str:
    if usage_log is not None:
        rows = usage_log.all()
        if max_calls is not None and len(rows) >= max_calls:
            raise BudgetExhausted("call ceiling")
        if token_ceiling is not None:
            spent = sum(
                int(r.get("prompt_tokens") or 0) + int(r.get("completion_tokens") or 0) for r in rows
            )
            if spent >= token_ceiling:
                raise BudgetExhausted("token ceiling")
    kwargs: dict[str, Any] = {
        "prompt": prompt,
        "role": role,
        "temperature": temperature,
        "model": model,
        "json_mode": json_mode,
    }
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
    try:
        raw = backend.complete(**kwargs)
    except TypeError:
        kwargs.pop("reasoning_effort", None)
        raw = backend.complete(**kwargs)
    _record_usage(backend, usage_log, role=role, model=model)
    return raw if isinstance(raw, str) else str(raw)


def extract_function_payload(raw: str, *, expected: str | None = None) -> tuple[str, str]:
    """Return (function_name, code). Accepts JSON {function, code} or raw def."""
    text = (raw or "").strip()
    if not text:
        return "", ""
    # Try JSON first.
    try:
        data = extract_json(text)
        if isinstance(data, dict):
            name = str(
                data.get("function")
                or data.get("function_name")
                or data.get("name")
                or data.get("symbol")
                or ""
            ).strip()
            code = str(data.get("code") or data.get("source") or "").strip()
            if not code and data.get("ops"):
                ops = data["ops"]
                if isinstance(ops, list) and ops and isinstance(ops[0], dict):
                    code = str(ops[0].get("code") or "")
                    name = name or str(ops[0].get("symbol") or "")
            if code:
                code = extract_python_source(code) or code
                def_name = _def_name(code) or name
                if expected and def_name and def_name != expected:
                    # Prefer expected name if body is present under wrong key.
                    if expected in code or f"def {expected}" in code:
                        def_name = expected
                return (def_name or expected or name or "", _normalize_def(code))
    except (ValueError, json.JSONDecodeError, TypeError):
        pass
    code = extract_python_source(text)
    name = _def_name(code) or (expected or "")
    return name, _normalize_def(code)


def _def_name(code: str) -> str | None:
    text = (code or "").strip()
    if not text:
        return None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        match = re.search(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text, re.M)
        return match.group(1) if match else None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    return None


def _normalize_def(code: str) -> str:
    text = extract_python_source(code) or (code or "")
    text = text.strip()
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def ast_compile_ok(source: str) -> tuple[bool, str]:
    try:
        ast.parse(source)
        compile(source, "<solver.py>", "exec")
    except SyntaxError as error:
        return False, str(error)
    return True, ""


def apply_function_to_solver(
    parent_source: str,
    function_name: str,
    function_code: str,
) -> tuple[str, str]:
    """REPLACE or ADD one top-level symbol. Returns (source, error)."""
    name = (function_name or _def_name(function_code) or "").strip()
    code = _normalize_def(function_code)
    if not name or not code.strip():
        return "", "empty function"
    if f"def {name}" not in code:
        return "", f"code missing def {name}"
    parent = parent_source if (parent_source or "").strip() else stub_solver_source()
    ok, err = ast_compile_ok(code)
    if not ok:
        return "", f"function syntax: {err}"
    # Prefer patch_apply path.
    proposal = proposal_from_raw_function(code, parent)
    if proposal is not None:
        applied = apply_proposal(parent, proposal)
        if applied.ok:
            return applied.source, ""
        # Fall through to explicit op.
    action = "REPLACE" if f"def {name}" in parent else "ADD"
    # If stubs present, REPLACE.
    try:
        tree = ast.parse(parent)
        names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        action = "REPLACE" if name in names else "ADD"
    except SyntaxError:
        pass
    proposal = PatchProposal(
        hypothesis=f"structured {action} {name}",
        ops=[PatchOp(action=action, symbol=name, code=code)],  # type: ignore[arg-type]
    )
    applied = apply_proposal(parent, proposal)
    if applied.ok:
        return applied.source, ""
    return "", applied.error or "patch failed"


def generate_function(
    backend: Any,
    *,
    function_name: str,
    model: str,
    spec: FormalSpec,
    parent_source: str = "",
    extra_context: dict[str, Any] | None = None,
    temperature: float = 0.4,
    usage_log: UsageLog | None = None,
    max_calls: int | None = None,
    token_ceiling: int | None = None,
    reasoning_effort: str | None = None,
) -> tuple[str, str, str]:
    """Ask LLM for one function. Returns (name, code, raw_error)."""
    prompt_file = {
        "construct": "construct.md",
        "repair": "repair.md",
        "improve": "improve.md",
        "solve": "solve.md",
        "mutate": "mutate.md",
        "crossover": "crossover.md",
        "repair_coder": "repair_coder.md",
    }.get(function_name, f"{function_name}.md")
    role = FUNCTION_ROLES.get(function_name, function_name)
    system = load_prompt(prompt_file)
    payload = {
        "function": function_name if function_name in REQUIRED_FUNCTIONS else "mutate_target",
        "spec": spec.model_dump(),
        "parent_solver_py": parent_source,
        "required_signature_hint": _signature_hint(function_name),
        "context": extra_context or {},
        "instruction": (
            f"Write ONLY the body of `{function_name}` as a complete Python def. "
            "Reply with JSON {\"function\": \"%s\", \"code\": \"def ...\"} "
            "or a raw Python def. No named published heuristics."
            % (function_name if function_name in REQUIRED_FUNCTIONS else "target")
        ),
    }
    prompt = system + "\n\nINPUT:\n" + json.dumps(payload, default=str)
    expected = function_name if function_name in REQUIRED_FUNCTIONS else None
    try:
        raw = llm_complete(
            backend,
            prompt=prompt,
            role=role,
            model=model,
            temperature=temperature,
            json_mode=True,
            usage_log=usage_log,
            max_calls=max_calls,
            token_ceiling=token_ceiling,
            reasoning_effort=reasoning_effort,
        )
    except BudgetExhausted:
        raise
    except Exception as error:  # noqa: BLE001
        return "", "", f"llm_error: {error}"
    name, code = extract_function_payload(raw, expected=expected)
    if expected and name and name != expected and f"def {expected}" in code:
        name = expected
    if expected:
        name = expected
    if not code.strip():
        return name or expected or "", "", "empty code"
    return name or expected or "", code, ""


def _signature_hint(name: str) -> str:
    return {
        "construct": "def construct(instance, rng): -> list[list[str]]",
        "repair": "def repair(instance, routes, rng): -> list[list[str]]",
        "improve": "def improve(instance, routes, rng): -> list[list[str]]",
        "solve": "def solve(instance, seed: int, time_limit_s: float): -> CandidateSolution|dict",
    }.get(name, "def <name>(...):")


def unit_test_functions(source: str, *, wall_clock_s: float = 5.0) -> dict[str, Any]:
    """Level-A micro checks via subprocess (never exec generated code in-process)."""
    from evrptw_autolab.sandbox.safe_exec import run_python_source

    result: dict[str, Any] = {
        "ok": False,
        "syntax_ok": False,
        "missing": [],
        "construct_ok": False,
        "repair_ok": False,
        "improve_ok": False,
        "solve_ok": False,
        "detail": "",
    }
    ok, err = ast_compile_ok(source)
    result["syntax_ok"] = ok
    if not ok:
        result["detail"] = err
        return result
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        result["detail"] = str(error)
        return result
    names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    missing = [n for n in REQUIRED_FUNCTIONS if n not in names]
    result["missing"] = missing
    if missing:
        result["detail"] = f"missing: {missing}"
        return result

    exec_result = run_python_source(source, wall_clock_s=wall_clock_s)
    if exec_result.timed_out:
        result["detail"] = "timeout"
        return result
    if exec_result.scan_errors:
        result["detail"] = exec_result.error or "; ".join(exec_result.scan_errors[:4])
        return result
    if exec_result.crashed and not exec_result.payload:
        result["detail"] = f"subprocess: {exec_result.error}"
        return result
    payload = exec_result.payload or {}
    for key in ("construct_ok", "repair_ok", "improve_ok", "solve_ok", "ok", "detail", "missing"):
        if key in payload:
            result[key] = payload[key]
    if not result.get("detail") and not result.get("ok"):
        result["detail"] = payload.get("detail") or exec_result.error or "unit failed"
    return result


def level_a_micro_pass(solver_dir: Path, *, limits: Any = None) -> dict[str, Any]:
    """Run executable/routing/charging/multi micro gates (no Schneider)."""
    from evrptw_autolab.sandbox.limits import limits_from_config
    from evrptw_autolab.sandbox.runner import run_solver

    limits = limits or limits_from_config()
    source = (solver_dir / "solver.py").read_text(encoding="utf-8")
    unit = unit_test_functions(source)
    out: dict[str, Any] = {"unit": unit, "gates": {}, "ok": False}
    if not unit.get("ok"):
        out["detail"] = unit.get("detail") or "unit failed"
        return out
    probes = [
        ("executable", micro_g1_one_customer(), False),
        ("routing", micro_g1_one_customer(), True),
        ("charging", micro_g2_needs_charge(), True),
        ("multi_customer", micro_g3_two_customers(), True),
    ]
    for name, probe, need_feasible in probes:
        report = run_solver(solver_dir, probe, seed=0, limits=limits)
        if name == "executable":
            passed = bool(report.parse_ok and not report.crashed and not report.timed_out)
        else:
            passed = bool(
                report.feasible and report.parse_ok and not report.crashed and not report.timed_out
            )
        if need_feasible and not passed:
            out["gates"][name] = False
            out["detail"] = f"level_a failed at {name}"
            return out
        out["gates"][name] = passed
        if not passed:
            out["detail"] = f"level_a failed at {name}"
            return out
    out["ok"] = True
    return out


def parts_from_source(source: str) -> dict[str, str]:
    """Extract top-level function sources by name."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    lines = source.splitlines(keepends=True)
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            start = node.lineno - 1
            end = (node.end_lineno or node.lineno) - 1
            block = "".join(lines[start : end + 1])
            if not block.endswith("\n"):
                block += "\n"
            out[node.name] = block
    return out


def reassemble_from_parts(parts: dict[str, str], imports: str | None = None) -> str:
    return assemble_solver_source(
        imports or DEFAULT_IMPORTS,
        parts.get("construct") or "def construct(instance, rng):\n    raise NotImplementedError\n",
        parts.get("repair") or "def repair(instance, routes, rng):\n    raise NotImplementedError\n",
        parts.get("improve") or "def improve(instance, routes, rng):\n    raise NotImplementedError\n",
        parts.get("solve") or "def solve(instance, seed: int, time_limit_s: float):\n    raise NotImplementedError\n",
    )
