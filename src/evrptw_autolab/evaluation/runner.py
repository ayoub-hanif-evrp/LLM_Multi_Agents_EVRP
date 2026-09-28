"""Fidelity-gated evaluation of a generated solver directory."""
from __future__ import annotations

import ast
from pathlib import Path

from evrptw_autolab.evaluation.fidelity import (
    HELDOUT_FAMILY,
    by_customer_count,
    family_representatives,
    partition_of,
    split_instances,
)
from evrptw_autolab.evaluation.metrics import summarize
from evrptw_autolab.problem.types import EvaluationReport, EVRPTWInstance
from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.sandbox.runner import run_solver
from evrptw_autolab.sandbox.static_scan import scan_directory

FIDELITY_ORDER = ("F0", "F1", "F2", "F3", "F4")
SMOKE_LIMITS = RunLimits(wall_clock_s=3.0)
_FORBIDDEN_SOLVER_CLASSES = frozenset({"EVRPTWInstance", "Node", "VehicleSpec", "CandidateSolution"})


def _module_defines(tree: ast.AST, name: str) -> bool:
    return any(isinstance(node, ast.FunctionDef) and node.name == name for node in getattr(tree, "body", []))


def _solve_contract_errors(tree: ast.AST, source: str) -> list[str]:
    """Static contract for solver.py. Feasibility is not required; stubs and wrong APIs are."""
    errors: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in _FORBIDDEN_SOLVER_CLASSES:
            errors.append(f"forbidden:redefine_{node.name}")
    solve = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "solve"), None)
    if solve is None:
        return errors
    args = [a.arg for a in solve.args.args]
    if len(args) < 3 or args[0] != "instance" or "seed" not in args or "time_limit_s" not in args:
        errors.append(f"bad_solve_signature:{','.join(args) or 'empty'}")
    returns_none = False
    returns_str = False
    for node in ast.walk(solve):
        if isinstance(node, ast.Return) and node.value is not None:
            if isinstance(node.value, ast.Constant) and node.value.value is None:
                returns_none = True
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                returns_str = True
            if isinstance(node.value, ast.Name) and node.value.id == "None":
                returns_none = True
    if returns_none:
        errors.append("stub:solve_returns_None")
    if returns_str:
        errors.append("stub:solve_returns_str")
    if "result = None" in source and "return result" in source:
        errors.append("stub:result_None")
    return errors


def next_fidelity(level: str) -> str | None:
    if level not in FIDELITY_ORDER:
        raise ValueError(f"unknown fidelity {level}")
    index = FIDELITY_ORDER.index(level)
    if index + 1 >= len(FIDELITY_ORDER):
        return None
    return FIDELITY_ORDER[index + 1]


def check_f0(solver_dir: Path, *, smoke: bool = True) -> list[str]:
    errors = scan_directory(solver_dir)
    py_files = sorted(solver_dir.rglob("*.py")) if solver_dir.exists() else []
    if not py_files:
        errors.append("missing:python")
    for path in py_files:
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except SyntaxError as error:
            errors.append(f"{path.name}:syntax_error:{error}")
            continue
        if path.name == "solver.py":
            if not _module_defines(tree, "solve"):
                errors.append("missing:solve")
            else:
                errors.extend(_solve_contract_errors(tree, text))
    solver_py = solver_dir / "solver.py"
    if not solver_py.exists():
        errors.append("missing:solver.py")
    # Static contract failures skip smoke (saves timeouts on infinite stubs).
    if errors or not smoke:
        return errors
    from evrptw_autolab.problem.private import smoke_instance

    report = run_solver(solver_dir, smoke_instance(1), seed=0, limits=SMOKE_LIMITS)
    if report.crashed or not report.parse_ok or report.timed_out:
        errors.append(f"smoke:crash:{(report.error or 'crash')[:400]}")
    return errors


def check_component_f0(solver_dir: Path, role: str) -> list[str]:
    """Interface gate for one specialist. Does not require a complete solver until Search writes."""
    errors: list[str] = []
    owned = {
        "routing": "routing.py",
        "charging": "charging.py",
        "search": "solver.py",
    }
    name = owned.get(role)
    if name is None:
        return check_f0(solver_dir, smoke=False)
    path = solver_dir / name
    if not path.exists():
        if role == "search":
            return check_f0(solver_dir, smoke=False)
        return errors
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as error:
        return [f"{name}:syntax_error:{error}"]
    if role == "search" and not _module_defines(tree, "solve"):
        errors.append("missing:solve")
    elif role == "search":
        errors.extend(_solve_contract_errors(tree, path.read_text(encoding="utf-8")))
    if role == "search":
        errors.extend(scan_directory(solver_dir))
    return errors


def instances_for_fidelity(
    discovery: list[EVRPTWInstance],
    level: str,
    *,
    max_instances: int | None = None,
) -> list[EVRPTWInstance]:
    if level == "F1":
        chosen = by_customer_count(discovery, [5])
    elif level == "F2":
        chosen = by_customer_count(discovery, [5, 10, 15])
    elif level in {"F3", "F4"}:
        chosen = family_representatives(discovery, large=True)
        if level == "F4":
            chosen = chosen + by_customer_count(discovery, [15])
    else:
        raise ValueError(f"unknown fidelity {level}")
    if any(partition_of(i) == "heldout" or str(i.metadata.get("family")) == HELDOUT_FAMILY for i in chosen):
        raise RuntimeError("held-out family leaked into fidelity selection")
    if max_instances is not None:
        chosen = chosen[:max_instances]
    return chosen


def evaluate_solver(
    solver_dir: Path,
    instances: list[EVRPTWInstance],
    *,
    seeds: list[int],
    limits: RunLimits | None = None,
) -> list[EvaluationReport]:
    reports: list[EvaluationReport] = []
    for instance in instances:
        for seed in seeds:
            reports.append(run_solver(solver_dir, instance, seed=seed, limits=limits))
    return reports


def evaluate_fidelity(
    solver_dir: Path,
    discovery: list[EVRPTWInstance],
    level: str,
    *,
    seeds: list[int] | None = None,
    limits: RunLimits | None = None,
    max_instances: int | None = None,
) -> dict[str, object]:
    f0 = check_f0(solver_dir)
    if f0:
        return {"level": "F0", "passed": False, "errors": f0, "summary": summarize([])}
    if level == "F0":
        return {"level": "F0", "passed": True, "errors": [], "summary": summarize([])}
    selected = instances_for_fidelity(discovery, level, max_instances=max_instances)
    reports = evaluate_solver(solver_dir, selected, seeds=seeds or [0], limits=limits)
    summary = summarize(reports)
    crashes = int(summary["crashes"])
    feasible_rate = float(summary.get("feasible_rate") or 0.0)
    execution_success = bool(summary["n"]) and crashes == 0
    # Feasibility gate is separate from "did it run".
    promotion_eligible = execution_success and feasible_rate >= 1.0
    return {
        "level": level,
        "passed": promotion_eligible,
        "execution_success": execution_success,
        "feasible_rate": feasible_rate,
        "promotion_eligible": promotion_eligible,
        "errors": [],
        "summary": summary,
        "n_instances": len(selected),
    }


def assert_discovery_split(instances: list[EVRPTWInstance]) -> list[EVRPTWInstance]:
    return split_instances(instances)["discovery"]
