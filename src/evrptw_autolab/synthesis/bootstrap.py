"""Generation-0 bootstrap: all five agents, same model, no hidden optimizer."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from evrptw_autolab.agents import ArchitectPlan, CriticDecision, build_team
from evrptw_autolab.evaluation.runner import check_f0, evaluate_fidelity
from evrptw_autolab.llm.usage import UsageLog
from evrptw_autolab.memory.lessons import LessonMemory
from evrptw_autolab.orchestration.activation import BOOTSTRAP_ROLES
from evrptw_autolab.orchestration.handshake import CODE_ROLES, apply_specialist_gated, report_brief
from evrptw_autolab.problem.types import EVRPTWInstance
from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.sandbox.runner import run_solver
from evrptw_autolab.synthesis.code_graph import CodeGraph, SolverNode
from evrptw_autolab.synthesis.compile_repair import compile_repair, evidence_repair, runtime_repair
from evrptw_autolab.orchestration.trajectory import append_trajectory
from evrptw_autolab.synthesis.contract import FAULT_ATLAS, INSTANCE_API, PROBLEM_BRIEF
from evrptw_autolab.synthesis.patching import code_hash


def bootstrap_solver(
    workspace: Path,
    backend: Any,
    *,
    model: str,
    instance: EVRPTWInstance,
    temperatures: dict[str, float] | None = None,
    discovery: list[EVRPTWInstance] | None = None,
    limits: RunLimits | None = None,
) -> dict[str, Any]:
    limits = limits or RunLimits(wall_clock_s=8.0)
    usage_log = UsageLog(workspace / "llm_calls.jsonl")
    team = build_team(backend, model=model, temperatures=temperatures, usage_log=usage_log)
    payload = {
        "task": "BOOTSTRAP",
        "problem": PROBLEM_BRIEF,
        "instance_api": INSTANCE_API,
        "fault_atlas": FAULT_ATLAS,
        "lab_ranking": FAULT_ATLAS["lab_ranking"],
        "instance_id": instance.instance_id,
        "family": instance.metadata.get("family"),
        "n_customers": len(instance.customer_ids),
        "held_out_family": "RC2 is never available during discovery; confirmation families are not used for evolution",
    }
    architect = team["architect"].run(payload)
    if not isinstance(architect, ArchitectPlan):
        raise TypeError("architect must return ArchitectPlan")
    # Generation-0 always uses all five roles, even if the architect omits BOOTSTRAP.
    active = list(BOOTSTRAP_ROLES)
    solver_dir = workspace / "candidates" / "S000"
    solver_dir.mkdir(parents=True, exist_ok=True)
    repair_payload = {**payload, "architect": architect.model_dump()}
    from evrptw_autolab.synthesis.patching import snapshot_files

    for role in CODE_ROLES:
        repair_payload["current_files"] = snapshot_files(solver_dir)
        apply_specialist_gated(solver_dir, team, role, repair_payload)
    f0_errors = compile_repair(solver_dir, team, repair_payload)

    def _run():
        return run_solver(solver_dir, instance, seed=0, limits=limits)

    report = _run()
    memory = LessonMemory(workspace / "memory" / "lessons.jsonl")
    report = runtime_repair(
        solver_dir, team, repair_payload, report, run=_run, max_rounds=3, memory=memory
    )
    report = evidence_repair(solver_dir, team, repair_payload, report, run=_run, max_rounds=2)
    f0_errors = check_f0(solver_dir)
    critic = team["critic"].run(
        {
            "parent": None,
            "evaluation": report_brief(report) | {"f0_errors": f0_errors},
            "lab_ranking": FAULT_ATLAS["lab_ranking"],
        }
    )
    if not isinstance(critic, CriticDecision):
        raise TypeError("critic must return CriticDecision")
    graph = CodeGraph(workspace / "code_graph")
    node = SolverNode(
        solver_id="S000",
        parent=None,
        code_hash=code_hash(solver_dir) if any(solver_dir.rglob("*.py")) else "",
        agent_role="architect",
        model=model,
        hypothesis=architect.hypothesis,
        status="ELITE" if report.feasible else "FAILED",
        path=str(solver_dir),
        evaluation_summary={
            "feasible": report.feasible,
            "vehicles": report.vehicles,
            "distance": report.total_distance,
            "error": report.error,
            "first_fault": report.first_fault,
        },
    )
    graph.add(node)
    memory.add(
        {"solver_id": "S000", "lesson": critic.lesson, "decision": critic.decision}
    )
    f1 = None
    if discovery:
        f1 = evaluate_fidelity(solver_dir, discovery, "F1", seeds=[0], max_instances=2)
    append_trajectory(
        workspace,
        {
            "cycle": 0,
            "solver_id": "S000",
            "elite_id": "S000",
            "parent_id": None,
            "instance_id": instance.instance_id,
            "activated": active,
            "architect_hypothesis": architect.hypothesis,
            "architect_target": architect.target,
            "decision": critic.decision if critic else None,
            "feasible": report.feasible,
            "vehicles": report.vehicles,
            "distance": report.total_distance,
            "first_fault": report.first_fault,
            "f0_errors": f0_errors,
            "code_hash": node.code_hash,
        },
    )
    return {
        "solver_id": "S000",
        "architect": architect.model_dump(),
        "critic": critic.model_dump() if critic else None,
        "evaluation": node.evaluation_summary,
        "path": str(solver_dir),
        "activated": active,
        "f0_errors": f0_errors,
        "f1": f1,
    }
