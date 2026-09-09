"""Bounded compile/interface repair. Surfaces errors to agents; does not write a solver."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from evrptw_autolab.agents import CodeProposal
from evrptw_autolab.evaluation.runner import check_f0
from evrptw_autolab.synthesis.patching import apply_proposal, snapshot_files

ROOT = Path(__file__).resolve().parents[3]


def max_compile_repair_rounds() -> int:
    path = ROOT / "configs" / "synthesis.yaml"
    if not path.exists():
        return 3
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return int((raw.get("bootstrap") or {}).get("max_compile_repair_rounds") or 3)


def role_for_f0_errors(errors: list[str]) -> str:
    blob = " ".join(errors).lower()
    if "charging.py" in blob:
        return "charging"
    if "routing.py" in blob:
        return "routing"
    return "search"


def compile_repair(
    solver_dir: Path,
    team: dict[str, Any],
    payload: dict[str, Any],
    *,
    max_rounds: int | None = None,
) -> list[str]:
    """Ask agents to fix F0 errors. Leaves invalid code invalid after retries."""
    rounds = max_compile_repair_rounds() if max_rounds is None else max_rounds
    errors = check_f0(solver_dir, smoke=False)
    for _ in range(max(0, rounds)):
        if not errors:
            return check_f0(solver_dir, smoke=False)
        role = role_for_f0_errors(errors)
        agent = team.get(role) or team.get("search")
        if agent is None:
            return check_f0(solver_dir, smoke=False)
        repair = agent.run(
            {
                **payload,
                "repair": errors,
                "current_files": snapshot_files(solver_dir),
                "instruction": (
                    "F0 failed. Emit a CodeProposal that writes complete Python files "
                    "fixing the listed errors. solver.py must define a module-level "
                    "solve(instance, seed, time_limit_s) returning {{'routes': ...}}."
                ),
            }
        )
        if isinstance(repair, CodeProposal) and repair.files:
            apply_proposal(solver_dir, repair)
        from evrptw_autolab.orchestration.handshake import recover_python_stub

        recover_python_stub(solver_dir, team, role, {**payload, "current_files": snapshot_files(solver_dir)})
        errors = check_f0(solver_dir, smoke=False)
    return check_f0(solver_dir, smoke=False)


def _write_solver_python(agent: Any, payload: dict[str, Any], solver_dir: Path, error: str) -> bool:
    import ast

    source = agent.write_python(
        {
            **payload,
            "runtime_error": error[-1500:],
            "current_files": snapshot_files(solver_dir),
            "instruction": (
                "The solver crashed at runtime. Fix THIS crash. Do not invent a new algorithm "
                "or change the search paradigm. Keep a module-level def solve. "
                "API: customer_ids / n_customers; customers is tuple[Node] not dict; "
                "vehicle singular (no vehicle_map); distance(Node,Node) from physics; "
                "do not redefine EVRPTWInstance. "
                f"Traceback:\n{error[-1500:]}"
            ),
        },
        filename="solver.py",
        marker="def solve",
    )
    if "def solve" not in source:
        return False
    try:
        ast.parse(source)
    except SyntaxError:
        return False
    (solver_dir / "solver.py").write_text(source, encoding="utf-8")
    return True


def runtime_repair(
    solver_dir: Path,
    team: dict[str, Any],
    payload: dict[str, Any],
    report: Any,
    *,
    run: Any,
    max_rounds: int = 3,
    memory: Any | None = None,
) -> Any:
    """Ask Search to rewrite crashing code. Failed after retries remains failed."""
    current = report
    for _ in range(max(0, max_rounds)):
        if not getattr(current, "crashed", False) and getattr(current, "parse_ok", True):
            return current
        agent = team.get("search")
        if agent is None:
            return current
        error = str(getattr(current, "error", "") or "crash")
        before = error[-240:]
        wrote = _write_solver_python(agent, payload, solver_dir, error)
        if not wrote:
            repair = agent.run(
                {
                    **payload,
                    "runtime_error": error[-1500:],
                    "current_files": snapshot_files(solver_dir),
                    "instruction": (
                        "The solver crashed at runtime. Rewrite solver.py so it runs. "
                        "Keep a module-level def solve. Fix this traceback; do not change paradigm."
                    ),
                }
            )
            if isinstance(repair, CodeProposal) and repair.files:
                apply_proposal(solver_dir, repair)
        compile_repair(solver_dir, team, payload, max_rounds=1)
        current = run()
        after = str(getattr(current, "error", "") or "")[-240:]
        if before == after and memory is not None:
            memory.add(
                {
                    "solver_id": str(payload.get("child_id") or payload.get("parent_id") or ""),
                    "lesson": f"raw-python rewrite did not change crash: {before[:160]}",
                    "decision": "REVISE",
                    "outcome": "FAILED",
                }
            )
    return current


def evidence_repair(
    solver_dir: Path,
    team: dict[str, Any],
    payload: dict[str, Any],
    report: Any,
    *,
    run: Any,
    max_rounds: int | None = None,
) -> Any:
    """Ask the fault owner to patch. Infeasible after retries remains infeasible."""
    from evrptw_autolab.orchestration.handshake import owner_for_report, recover_python_stub
    from evrptw_autolab.synthesis.contract import FAULT_ATLAS

    settings_rounds = 2 if max_rounds is None else max_rounds
    current = report
    for _ in range(max(0, settings_rounds)):
        if getattr(current, "crashed", False) or not getattr(current, "parse_ok", True):
            return current
        if getattr(current, "feasible", False):
            return current
        role = owner_for_report(current)
        agent = team.get(role) or team.get("search")
        if agent is None:
            return current
        fault = getattr(current, "first_fault", None) or {}
        files = snapshot_files(solver_dir)
        repair = agent.run(
            {
                **payload,
                "first_fault": fault,
                "fault_atlas": FAULT_ATLAS,
                "current_files": files,
                "instruction": (
                    "The lab oracle rejected the incumbent. Fix ONLY the first-fault family "
                    f"{fault.get('family')} at node {fault.get('node_id')}: {fault.get('detail')}. "
                    "Invent the repair. The laboratory does not supply construction, "
                    "station-insertion, merge, or acceptance recipes."
                ),
            }
        )
        if isinstance(repair, CodeProposal) and repair.files:
            apply_proposal(solver_dir, repair)
        recover_python_stub(solver_dir, team, role, {**payload, "current_files": snapshot_files(solver_dir)})
        if role != "search":
            search = team.get("search")
            if search is not None:
                wire = search.run(
                    {
                        **payload,
                        "first_fault": fault,
                        "current_files": snapshot_files(solver_dir),
                        "instruction": (
                            "A specialist just patched a helper. Rewrite solver.py so solve() "
                            "imports and uses that helper if it exists. Visit every customer "
                            "exactly once. Invent construction and search. Include any imports "
                            "you use."
                        ),
                    }
                )
                if isinstance(wire, CodeProposal) and wire.files:
                    apply_proposal(solver_dir, wire)
                recover_python_stub(
                    solver_dir, team, "search", {**payload, "current_files": snapshot_files(solver_dir)}
                )
        compile_repair(solver_dir, team, payload, max_rounds=1)
        current = run()
    return current
