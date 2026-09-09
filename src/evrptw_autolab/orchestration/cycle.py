"""One gated research cycle over the fixed five-agent team."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from evrptw_autolab.agents import ArchitectPlan, CriticDecision, build_team
from evrptw_autolab.evaluation.attribution import matched_delta, role_outcomes
from evrptw_autolab.evaluation.ranking import child_is_better, panel_is_better
from evrptw_autolab.evaluation.runner import check_f0, evaluate_solver
from evrptw_autolab.llm.usage import UsageLog
from evrptw_autolab.memory.archive import Archive
from evrptw_autolab.memory.lessons import LessonMemory
from evrptw_autolab.orchestration.activation import roles_for_phase, roles_for_plan
from evrptw_autolab.orchestration.handshake import (
    CODE_ROLES,
    apply_specialist_gated,
    cycle_settings,
    owner_for_report,
    report_brief,
)
from evrptw_autolab.problem.types import EVRPTWInstance
from evrptw_autolab.sandbox.limits import RunLimits, limits_from_synthesis
from evrptw_autolab.sandbox.runner import run_solver
from evrptw_autolab.synthesis.code_graph import CodeGraph, SolverNode
from evrptw_autolab.synthesis.compile_repair import compile_repair, evidence_repair, runtime_repair
from evrptw_autolab.orchestration.trajectory import append_trajectory
from evrptw_autolab.synthesis.contract import FAULT_ATLAS, INSTANCE_API, PROBLEM_BRIEF
from evrptw_autolab.synthesis.patching import (
    code_hash,
    copy_solver_tree,
    next_free_solver_id,
    snapshot_files,
)


def next_solver_id(graph: CodeGraph, workspace: Path | None = None) -> str:
    taken = set(graph.nodes)
    if workspace is None:
        index = len(graph.nodes)
        return f"S{index:03d}"
    return next_free_solver_id(workspace / "candidates", taken)


def _limits(limits: RunLimits | None) -> RunLimits:
    return limits if limits is not None else limits_from_synthesis()


def _phase(f0_errors: list[str], report: Any) -> str:
    if f0_errors or getattr(report, "crashed", False) or not getattr(report, "parse_ok", True):
        return "DEBUG"
    if not getattr(report, "feasible", False):
        return "CONTRACT"
    return "OPTIMIZE"


def run_cycle(
    workspace: Path,
    backend: Any,
    *,
    model: str,
    parent_id: str,
    instance: EVRPTWInstance,
    temperatures: dict[str, float] | None = None,
    limits: RunLimits | None = None,
    acceptance_panel: list[EVRPTWInstance] | None = None,
) -> dict[str, Any]:
    limits = _limits(limits)
    settings = cycle_settings()
    usage_log = UsageLog(workspace / "llm_calls.jsonl")
    team = build_team(backend, model=model, temperatures=temperatures, usage_log=usage_log)
    parent_dir = workspace / "candidates" / parent_id
    parent_f0 = check_f0(parent_dir)
    parent_report = run_solver(parent_dir, instance, seed=0, limits=limits)
    memory = LessonMemory(workspace / "memory" / "lessons.jsonl")
    phase = _phase(parent_f0, parent_report)
    shared = {
        "task": "CYCLE",
        "problem": PROBLEM_BRIEF,
        "instance_api": INSTANCE_API,
        "fault_atlas": FAULT_ATLAS,
        "parent_id": parent_id,
        "phase": phase,
        "current_files": snapshot_files(parent_dir),
        "lessons": memory.retrieve(
            {
                "target": phase,
                "family": str((parent_report.first_fault or {}).get("family") or ""),
                "instance_family": str(instance.metadata.get("family") or ""),
            },
            k=5,
        ),
        "evaluation": report_brief(parent_report) | {"f0_errors": parent_f0, "phase": phase},
        "lab_ranking": FAULT_ATLAS["lab_ranking"],
    }
    if phase == "DEBUG":
        shared["instruction"] = (
            "DEBUG phase: the elite crashed or failed executable F0. Target SEARCH. "
            "Do not change search paradigm. Ask Search to fix the crash."
        )

        def _parent_run():
            return run_solver(parent_dir, instance, seed=0, limits=limits)

        parent_report = runtime_repair(
            parent_dir,
            team,
            shared,
            parent_report,
            run=_parent_run,
            max_rounds=int(settings["runtime_repair_rounds"]),
            memory=memory,
        )
        parent_f0 = check_f0(parent_dir)
        shared["current_files"] = snapshot_files(parent_dir)
        shared["evaluation"] = report_brief(parent_report) | {"f0_errors": parent_f0, "phase": phase}
    elif phase == "OPTIMIZE":
        shared["instruction"] = (
            "OPTIMIZE phase: elite is feasible. Reduce vehicles first, then total distance. "
            "Keep every customer served once and stay feasible. Invent merges and charging yourself."
        )
    architect = team["architect"].run(shared)
    if not isinstance(architect, ArchitectPlan):
        raise TypeError("architect must return ArchitectPlan")
    if phase == "DEBUG":
        active = roles_for_phase(phase, architect)
    else:
        active = roles_for_plan(architect)
        if not parent_report.feasible and not parent_report.crashed:
            owner = owner_for_report(parent_report)
            for role in (owner, "charging", "search", "critic"):
                if role not in active:
                    active.append(role)
    graph = CodeGraph(workspace / "code_graph")
    child_id = next_solver_id(graph, workspace)
    child_dir = workspace / "candidates" / child_id
    copy_solver_tree(parent_dir, child_dir)
    specialist_payload = {
        **shared,
        "architect": architect.model_dump(),
        "child_id": child_id,
        "phase": phase,
    }
    for role in CODE_ROLES:
        if role not in active:
            continue
        apply_specialist_gated(child_dir, team, role, specialist_payload)
    f0_errors = compile_repair(child_dir, team, specialist_payload)

    def _run():
        return run_solver(child_dir, instance, seed=0, limits=limits)

    child_report = _run()
    child_report = runtime_repair(
        child_dir,
        team,
        specialist_payload,
        child_report,
        run=_run,
        max_rounds=int(settings["runtime_repair_rounds"]),
        memory=memory,
    )
    child_report = evidence_repair(
        child_dir,
        team,
        specialist_payload,
        child_report,
        run=_run,
        max_rounds=int(settings["evidence_repair_rounds"]),
    )
    f0_errors = check_f0(child_dir)
    critic = None
    if "critic" in active:
        critic = team["critic"].run(
            {
                "parent": report_brief(parent_report),
                "child": report_brief(child_report) | {"f0_errors": f0_errors},
                "delta": matched_delta(parent_report, child_report),
                "lab_ranking": FAULT_ATLAS["lab_ranking"],
            }
        )
        if not isinstance(critic, CriticDecision):
            raise TypeError("critic must return CriticDecision")
    decision = critic.decision if critic is not None else "REVISE"
    if acceptance_panel:
        parent_panel = evaluate_solver(parent_dir, acceptance_panel, seeds=[0], limits=limits)
        child_panel = evaluate_solver(child_dir, acceptance_panel, seeds=[0], limits=limits)
        better = panel_is_better(parent_panel, child_panel)
    else:
        better = child_is_better(parent_report, child_report)
    attempted = {
        "feasible": child_report.feasible,
        "vehicles": child_report.vehicles,
        "distance": child_report.total_distance,
        "first_fault": child_report.first_fault,
        "delta": matched_delta(parent_report, child_report),
        "roles": role_outcomes(
            active,
            parent=parent_report,
            child=child_report,
            architect_target=architect.target,
            fault_repaired=bool(parent_report.first_fault)
            and (parent_report.first_fault or {}).get("family") not in {"OK", None}
            and (child_report.first_fault or {}).get("family") == "OK",
        ),
    }
    # DEBUG: promote only real progress; never REVERT-wipe a Search attempt.
    if phase == "DEBUG":
        fewer_f0 = len(f0_errors) < len(parent_f0)
        child_runs = (not child_report.crashed) and child_report.parse_ok and (not child_report.timed_out)
        if better or child_runs or fewer_f0:
            decision = "RETAIN"
            better = True
        else:
            decision = "REVISE"
            better = False
            # Keep child files for inspection; elite stays parent.
    elif phase == "OPTIMIZE":
        # Never replace a feasible elite with a crash or infeasible child.
        if parent_report.feasible and (child_report.crashed or not child_report.feasible):
            decision = "REVERT" if child_report.crashed else "REVISE"
            better = False
        elif better:
            decision = "RETAIN"
        else:
            decision = "REVISE"
            better = False
    elif parent_report.feasible and child_report.crashed:
        decision = "REVERT"
    elif better:
        decision = "RETAIN"
    if decision == "REVERT":
        # Candidates are immutable: keep failed child on disk; elite pointer stays parent.
        better = False
        decision = "REVERT"
    status = "ELITE" if better else decision
    node = SolverNode(
        solver_id=child_id,
        parent=parent_id,
        code_hash=code_hash(child_dir) if any(child_dir.rglob("*.py")) else "",
        agent_role="architect",
        model=model,
        hypothesis=architect.hypothesis,
        status=status,
        path=str(child_dir),
        evaluation_summary={
            "feasible": child_report.feasible,
            "vehicles": child_report.vehicles,
            "distance": child_report.total_distance,
            "error": child_report.error,
            "first_fault": child_report.first_fault,
        },
    )
    graph.add(node)
    if critic is not None:
        memory.add({"solver_id": child_id, "lesson": critic.lesson, "decision": critic.decision})
    Archive(workspace / "archive.jsonl").add(
        {"solver_id": child_id, "activated": active, "why": architect.target, "decision": decision}
    )
    elite_id = child_id if better else parent_id
    delta = attempted["delta"]
    append_trajectory(
        workspace,
        {
            "cycle": len(graph.nodes) - 1,
            "solver_id": child_id,
            "elite_id": elite_id,
            "parent_id": parent_id,
            "instance_id": instance.instance_id,
            "activated": active,
            "architect_hypothesis": architect.hypothesis,
            "architect_target": architect.target,
            "phase": phase,
            "decision": decision,
            "better": better,
            "parent_feasible": parent_report.feasible,
            "parent_vehicles": parent_report.vehicles,
            "parent_distance": parent_report.total_distance,
            "parent_fault": (parent_report.first_fault or {}).get("family"),
            "feasible": child_report.feasible,
            "vehicles": child_report.vehicles,
            "distance": child_report.total_distance,
            "first_fault": child_report.first_fault,
            "attempted_feasible": attempted["feasible"],
            "attempted_vehicles": attempted["vehicles"],
            "attempted_distance": attempted["distance"],
            "vehicles_delta": delta["vehicles_delta"],
            "distance_delta": delta["distance_delta"],
            "fault_repaired": bool(parent_report.first_fault)
            and (parent_report.first_fault or {}).get("family") not in {"OK", None}
            and (attempted["first_fault"] or {}).get("family") == "OK",
            "f0_errors": f0_errors,
            "code_hash": node.code_hash,
            "critic_lesson": critic.lesson if critic else None,
            "role_outcomes": attempted["roles"],
        },
    )
    return {
        "solver_id": child_id,
        "elite_id": elite_id,
        "activated": active,
        "why": architect.target,
        "decision": decision,
        "evaluation": node.evaluation_summary,
        "architect": architect.model_dump(),
        "critic": critic.model_dump() if critic else None,
        "f0_errors": f0_errors,
        "phase": phase,
    }
