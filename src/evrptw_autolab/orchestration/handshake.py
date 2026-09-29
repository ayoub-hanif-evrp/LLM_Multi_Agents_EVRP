"""Sequential specialist gate. Interface check between roles; not a hidden solver."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

import yaml

from evrptw_autolab.agents import CodeProposal, HandshakeVerdict
from evrptw_autolab.agents.base import is_python_stub
from evrptw_autolab.evaluation.runner import check_component_f0
from evrptw_autolab.problem.types import EvaluationReport

ROOT = Path(__file__).resolve().parents[3]
CODE_ROLES = ("routing", "charging", "search")
OWNED_FILES = {
    "routing": ("routing.py", "def "),
    "charging": ("charging.py", "def "),
    "search": ("solver.py", "def solve"),
}
FAULT_OWNERS = {
    "VISIT": "routing",
    "DEPOT": "routing",
    "CAPACITY": "routing",
    "WINDOW": "charging",
    "BATTERY": "charging",
    "CHARGE_POLICY": "charging",
    "CRASH": "search",
    "PARSE": "search",
    "OK": "search",
}


def cycle_settings() -> dict[str, Any]:
    path = ROOT / "configs" / "synthesis.yaml"
    cycle = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cycle = dict(raw.get("cycle") or {})
    return {
        "wall_clock_s": float(cycle.get("wall_clock_s") or 20.0),
        "evidence_repair_rounds": int(cycle.get("evidence_repair_rounds") or 2),
        "handshake": bool(cycle.get("handshake", True)),
        "max_handshake_returns": int(cycle.get("max_handshake_returns") or 1),
        "runtime_repair_rounds": int(cycle.get("runtime_repair_rounds") or 3),
    }


def owner_for_family(family: str) -> str:
    return str(FAULT_OWNERS.get(family, "search"))


def owner_for_report(report: EvaluationReport) -> str:
    if report.crashed or not report.parse_ok:
        return "search"
    family = str((report.first_fault or {}).get("family") or "OK")
    return owner_for_family(family)


def pick_cycle_instance(
    solver_dir: Path,
    instances: list[Any],
    *,
    limits: Any | None = None,
) -> tuple[Any, EvaluationReport]:
    """Curriculum: 1-customer smoke, then 2-customer, then an unsolved discovery case."""
    from evrptw_autolab.problem.private import smoke_instance
    from evrptw_autolab.sandbox.limits import RunLimits
    from evrptw_autolab.sandbox.runner import run_solver

    if not instances:
        raise ValueError("pick_cycle_instance needs at least one instance")
    probe = limits or RunLimits(wall_clock_s=8.0)
    for n_customers in (1, 2):
        smoke = smoke_instance(n_customers)
        report = run_solver(solver_dir, smoke, seed=0, limits=probe)
        if report.crashed or not report.parse_ok or not report.feasible:
            return smoke, report
    first = instances[0]
    first_report = run_solver(solver_dir, first, seed=0, limits=probe)
    if not first_report.feasible:
        return first, first_report
    for instance in instances[1:]:
        report = run_solver(solver_dir, instance, seed=0, limits=probe)
        if not report.crashed and not report.feasible:
            return instance, report
    return first, first_report


def report_brief(report: EvaluationReport) -> dict[str, Any]:
    return {
        "feasible": report.feasible,
        "vehicles": report.vehicles,
        "distance": report.total_distance,
        "error": report.error[-1500:],
        "crashed": report.crashed,
        "first_fault": report.first_fault or {},
    }


def recover_python_stub(
    solver_dir: Path,
    team: dict[str, Any],
    role: str,
    payload: dict[str, Any],
) -> bool:
    """JSON mode often emits a comment placeholder. Ask the same role for raw Python."""
    import ast

    spec = OWNED_FILES.get(role)
    if spec is None:
        return False
    name, marker = spec
    path = solver_dir / name
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if not is_python_stub(text, marker):
        return False
    agent = team.get(role)
    if agent is None:
        return False
    source = agent.write_python(
        {
            **payload,
            "instruction": (
                f"Your JSON left {name} as a placeholder comment. "
                f"Write complete Python for {name}. It must contain `{marker.strip()}`. "
                "Invent the algorithm; the laboratory does not supply a recipe."
            ),
        },
        filename=name,
        marker=marker,
    )
    if marker not in source:
        return False
    try:
        ast.parse(source)
    except SyntaxError:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return True


def apply_specialist_gated(
    solver_dir: Path,
    team: dict[str, Any],
    role: str,
    payload: dict[str, Any],
    *,
    max_returns: int | None = None,
) -> list[str]:
    """Write one specialist, then gate on that component before the next role runs."""
    from evrptw_autolab.synthesis.compile_repair import compile_repair
    from evrptw_autolab.synthesis.contract import FAULT_ATLAS
    from evrptw_autolab.synthesis.patching import apply_proposal, snapshot_files

    # Always see the latest sibling files written by prior roles.
    payload = {**payload, "current_files": snapshot_files(solver_dir)}
    settings = cycle_settings()
    if not settings["handshake"]:
        proposal = team[role].run(payload)
        if isinstance(proposal, CodeProposal) and proposal.files:
            apply_proposal(solver_dir, proposal)
        recover_python_stub(solver_dir, team, role, payload)
        return check_component_f0(solver_dir, role)
    returns = settings["max_handshake_returns"] if max_returns is None else max_returns
    # Prefer raw Python for code roles (hypothesis JSON is optional via agent.run schemas).
    wrote = False
    if role in OWNED_FILES:
        agent = team.get(role)
        if agent is not None:
            name, marker = OWNED_FILES[role]
            try:
                source = agent.write_python(
                    {
                        **payload,
                        "owned_role": role,
                        "fault_atlas": FAULT_ATLAS,
                        "instruction": (
                            f"Write complete Python for {name}. It must contain `{marker.strip()}`. "
                            "Invent the algorithm; the laboratory does not supply a recipe."
                        ),
                    },
                    filename=name,
                    marker=marker,
                )
                if marker in source:
                    import ast

                    ast.parse(source)
                    (solver_dir / name).write_text(source, encoding="utf-8")
                    wrote = True
            except (SyntaxError, ValueError, TypeError, AttributeError, RuntimeError):
                wrote = False
    if not wrote:
        proposal = team[role].run({**payload, "owned_role": role, "fault_atlas": FAULT_ATLAS})
        if isinstance(proposal, CodeProposal) and proposal.files:
            apply_proposal(solver_dir, proposal)
    recover_python_stub(solver_dir, team, role, {**payload, "current_files": snapshot_files(solver_dir)})
    errors = check_component_f0(solver_dir, role)
    if errors:
        compile_repair(solver_dir, team, payload, max_rounds=1)
        errors = check_component_f0(solver_dir, role)
    if errors and returns > 0 and "critic" in team:
        try:
            verdict = team["critic"].handshake(
                {
                    "task": "HANDSHAKE",
                    "owned_role": role,
                    "component_errors": errors,
                    "current_files": snapshot_files(solver_dir, max_chars=1200),
                    "fault_atlas": FAULT_ATLAS,
                }
            )
        except (ValueError, TypeError, AttributeError):
            owner = role.upper() if role.upper() in {"ROUTING", "CHARGING", "SEARCH"} else "SEARCH"
            verdict = HandshakeVerdict(
                verdict="RETURN",
                owner=cast(Literal["ROUTING", "CHARGING", "SEARCH", "ARCHITECTURE"], owner),
                instruction="; ".join(errors)[:400],
            )
        if getattr(verdict, "verdict", "PASS") == "RETURN":
            repair = team[role].run(
                {
                    **payload,
                    "handshake_return": getattr(verdict, "instruction", "") or errors,
                    "repair": errors,
                    "current_files": snapshot_files(solver_dir),
                    "instruction": (
                        f"The lab gate returned {role} code. Rewrite the owned file so it parses. "
                        f"Instruction: {getattr(verdict, 'instruction', '')}"
                    ),
                }
            )
            if isinstance(repair, CodeProposal) and repair.files:
                apply_proposal(solver_dir, repair)
            recover_python_stub(solver_dir, team, role, {**payload, "current_files": snapshot_files(solver_dir)})
            errors = check_component_f0(solver_dir, role)
    return errors
