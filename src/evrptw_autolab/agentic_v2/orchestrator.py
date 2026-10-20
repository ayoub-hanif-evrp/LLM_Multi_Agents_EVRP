"""Five-agent loop. The independent evaluator, not the critic, decides feasibility."""
from __future__ import annotations

import copy
import time
from typing import Any

from evrptw_autolab.agentic_v2.actions import apply_relocations, insert_charges, solution_from_plan
from evrptw_autolab.agentic_v2.executor import execute_generated_solver
from evrptw_autolab.agentic_v2.instance_context import (
    agent_for_fault,
    customer_ids,
    spec_payload,
    summarize_instance,
)
from evrptw_autolab.agents.base import extract_json, extract_python_source
from evrptw_autolab.llm.usage import BudgetExhausted, UsageCollector
from evrptw_autolab.problem.v2.evaluator import evaluate_solution_v2
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2

_EXPLICIT_CUSTOMER_LIMIT = 15


def _ask(collector: UsageCollector, backend: Any, model: str, role: str, prompt: str) -> dict[str, Any]:
    raw = collector.complete(backend, prompt=prompt, role=role, temperature=0.2, model=model, json_mode=True)
    try:
        payload = extract_json(raw)
    except (ValueError, TypeError):
        payload = {"raw": raw, "parse_error": True}
    return payload


def _report_dict(spec: ProblemSpecV2, solution: SolutionV2) -> dict[str, Any]:
    report = evaluate_solution_v2(spec, solution)
    fault = None if report.first_fault is None else report.first_fault.family
    detail = "" if report.first_fault is None else report.first_fault.detail
    return {
        "feasible": bool(report.feasible),
        "objective_key": [float(value) for value in report.objective_key],
        "vehicles": int(report.vehicles),
        "distance": float(report.total_distance),
        "duration": float(report.total_duration),
        "first_fault": fault,
        "fault_detail": detail,
        "violations": [item.family for item in report.violations[:8]],
    }


def _snapshot(solution: SolutionV2) -> SolutionV2:
    return SolutionV2(
        routes=copy.deepcopy(solution.routes),
        vehicle_assignments=list(solution.vehicle_assignments),
        metadata=dict(solution.metadata),
    )


def _better(candidate: dict[str, Any], incumbent: dict[str, Any] | None) -> bool:
    if not candidate["feasible"]:
        return False
    if incumbent is None or not incumbent["feasible"]:
        return True
    return tuple(candidate["objective_key"]) < tuple(incumbent["objective_key"])


def _route_ids(solution: SolutionV2) -> list[list[str]]:
    return [[stop.node_id for stop in route] for route in solution.routes]


def _solution_dump(solution: SolutionV2) -> dict[str, Any]:
    return {
        "vehicle_assignments": list(solution.vehicle_assignments),
        "routes": [
            [
                {
                    "node_id": stop.node_id,
                    "event": stop.event,
                    "charge_amount": stop.charge_amount,
                    "charge_technology": stop.charge_technology,
                    "target_soc": stop.target_soc,
                }
                for stop in route
            ]
            for route in solution.routes
        ],
    }


def solve_with_agents(
    spec: ProblemSpecV2,
    *,
    backend: Any,
    model: str,
    max_rounds: int = 3,
    max_llm_calls: int = 16,
    source_sha256: str | None = None,
    source_path: str | None = None,
) -> dict[str, Any]:
    """Collaborate on one instance and return the best independently feasible incumbent, if any."""
    started = time.monotonic()
    collector = UsageCollector(max_calls=max_llm_calls, max_tokens=80000 if len(customer_ids(spec)) > _EXPLICIT_CUSTOMER_LIMIT else 24000)
    customers = customer_ids(spec)
    mode = "explicit_routes" if len(customers) <= _EXPLICIT_CUSTOMER_LIMIT else "generated_solver"
    summary = summarize_instance(spec)
    trace: list[dict[str, Any]] = []
    incumbent_solution: SolutionV2 | None = None
    incumbent_report: dict[str, Any] | None = None
    feedback = "No solution has been evaluated yet."

    try:
        architect = _ask(
            collector,
            backend,
            model,
            "architect",
            (
                "You are the EVRP Architect. Read this instance summary and return JSON only.\n"
                "Do not invent constraints that are not in capabilities. Do not change the native objective.\n"
                '{"objective":"...","hard_constraints":["..."],"strategy":"...","activate":["routing","charging","optimization","critic"]}\n'
                + json_summary(summary)
            ),
        )
        trace.append({"role": "architect", "output": architect})
        allowed = set(summary["capabilities"])
        architect["hard_constraints"] = [name for name in architect.get("hard_constraints") or [] if name in allowed]

        if mode == "generated_solver":
            incumbent_solution, incumbent_report, trace = _generated_loop(
                spec, collector, backend, model, summary, feedback, trace, max_rounds
            )
        else:
            incumbent_solution, incumbent_report, trace = _explicit_loop(
                spec, collector, backend, model, summary, feedback, trace, max_rounds
            )
    except BudgetExhausted as error:
        trace.append({"role": "controller", "note": f"budget_exhausted:{error}"})
        if incumbent_report is None:
            incumbent_report = {
                "feasible": False,
                "first_fault": "NO_SOLUTION",
                "objective_key": [],
                "fault_detail": str(error),
            }

    report = incumbent_report or {"feasible": False, "first_fault": "NO_SOLUTION", "objective_key": []}
    return {
        "family": spec.family,
        "instance_id": spec.instance_id,
        "source_path": source_path,
        "source_sha256": source_sha256,
        "model": model,
        "mode": mode,
        "method": "agentic_v2",
        "classical_alns_used": False,
        "feasible": bool(report.get("feasible")),
        "evaluation": report,
        "solution": None if incumbent_solution is None else _solution_dump(incumbent_solution),
        "agent_trace": trace,
        "llm_calls": collector.logical_calls,
        "llm_tokens": collector.total_tokens,
        "wall_s": round(time.monotonic() - started, 3),
        "status": "FEASIBLE" if report.get("feasible") else _status(report),
    }


def json_summary(summary: dict[str, Any]) -> str:
    import json

    return json.dumps(summary)


def _status(report: dict[str, Any]) -> str:
    fault = str(report.get("first_fault") or "")
    if fault in {"timeout", "EXECUTION_ERROR"}:
        return "EXECUTION_ERROR"
    if fault == "NO_SOLUTION" and "budget" in str(report.get("fault_detail") or ""):
        return "NOT_RUN_BUDGET"
    if fault == "NO_SOLUTION":
        return "MODEL_FAILURE"
    return "INFEASIBLE_OUTPUT"


def _explicit_loop(
    spec: ProblemSpecV2,
    collector: UsageCollector,
    backend: Any,
    model: str,
    summary: dict[str, Any],
    feedback: str,
    trace: list[dict[str, Any]],
    max_rounds: int,
) -> tuple[SolutionV2 | None, dict[str, Any] | None, list[dict[str, Any]]]:
    incumbent_solution: SolutionV2 | None = None
    incumbent_report: dict[str, Any] | None = None
    latest_solution: SolutionV2 | None = None
    latest_report: dict[str, Any] | None = None

    def _keep(solution: SolutionV2, report: dict[str, Any]) -> None:
        nonlocal incumbent_solution, incumbent_report, latest_solution, latest_report
        latest_solution = _snapshot(solution)
        latest_report = report
        if _better(report, incumbent_report):
            incumbent_solution = latest_solution
            incumbent_report = report

    previous_fault: str | None = None
    for round_index in range(max_rounds):
        if previous_fault in {"BATTERY", "WINDOW", "CHARGE_POLICY", "DURATION"}:
            routing = _ask(
                collector,
                backend,
                model,
                "routing",
                (
                    "You are the Routing Agent. The explicit route was infeasible. "
                    "Write Python defining solve(instance: dict) -> dict. "
                    "Use instance['customer_ids'], instance['vehicles'], and instance['travel']. "
                    "Open a separate route when two customers cannot share a vehicle without passing a due time "
                    "or exceeding battery_capacity. A route may contain one customer. "
                    "Do not import libraries and do not call a classical solver. "
                    "Return {\"code\": \"def solve(instance):\\n    ...\"}.\n"
                    f"Previous fault: {feedback}\n"
                    + json_summary(summary)
                ),
            )
            source = extract_python_source(str(routing.get("code") or ""))
            executed = execute_generated_solver(source, spec_payload(spec))
            trace.append(
                {
                    "role": "routing",
                    "round": round_index,
                    "mode": "generated_solver",
                    "ok": executed["ok"],
                    "errors": executed["errors"],
                    "source": source,
                }
            )
            payload = executed["routes"] if executed["ok"] and isinstance(executed["routes"], dict) else {"routes": []}
            solution, route_errors = solution_from_plan(spec, payload)
            route_errors = list(route_errors) + list(executed["errors"])
        else:
            routing = _ask(
                collector,
                backend,
                model,
                "routing",
                (
                    "You are the Routing Agent. Return JSON only. Visit every customer id from the summary exactly once.\n"
                    "Use several routes when a hop arrives after due_time or a round trip exceeds battery_capacity. "
                    "Travel time equals distance divided by velocity. Charging cannot shorten a late hop. "
                    "Do not put station ids in customers; the charging agent inserts stations. "
                    "Pickup must precede its delivery on the same vehicle. Use a vehicle_type id from the summary.\n"
                    "Schema: {\"routes\":[{\"vehicle_type\":\"<id>\",\"customers\":[\"<customer id>\"]}]}\n"
                    "Do not invent ids and do not copy placeholder text.\n"
                    f"Round {round_index}. Evaluator feedback: {feedback}\n"
                    + json_summary(summary)
                ),
            )
            trace.append({"role": "routing", "round": round_index, "output": routing})
            solution, route_errors = solution_from_plan(spec, routing)
        report = _report_dict(spec, solution)
        report["route_errors"] = route_errors
        _keep(solution, report)
        charging = _ask(
            collector,
            backend,
            model,
            "charging",
            (
                "You are the Charging Agent. Return JSON only.\n"
                "after_stop must be a node id that already appears in the current routes.\n"
                "station_id must be a station from the summary.\n"
                "If full_recharge is true, set target_soc to the vehicle battery_capacity and omit charge_amount.\n"
                "If multiple_charge_technologies is true, set charge_amount and charge_technology; do not omit them.\n"
                "Use an empty insertions list when no station is required.\n"
                "Schema: {\"insertions\":[{\"route\":0,\"after_stop\":\"<existing stop>\",\"station_id\":\"<station>\",\"target_soc\":0}]}\n"
                f"Current routes: {_route_ids(solution)}\n"
                f"Current faults: {report}\n"
                + json_summary(
                    {
                        "full_recharge": summary["capabilities"]["full_recharge"],
                        "multiple_charge_technologies": summary["capabilities"]["multiple_charge_technologies"],
                        "nonlinear_charging": summary["capabilities"]["nonlinear_charging"],
                        "vehicles": summary["vehicles"],
                        "stations": [node for node in summary["nodes"] if node["kind"] == "station"][:20],
                    }
                )
            ),
        )
        trace.append({"role": "charging", "round": round_index, "output": charging})
        charge_errors = insert_charges(spec, solution, charging)
        report = _report_dict(spec, solution)
        report["charge_errors"] = charge_errors
        _keep(solution, report)
        optimization = _ask(
            collector,
            backend,
            model,
            "optimization",
            (
                "You are the Optimization Agent. Propose at most four customer relocations on the current routes.\n"
                "Return an empty move list when you have no bounded improvement.\n"
                '{"moves":[{"op":"relocate","customer":"id","to_route":0,"position":1}]}\n'
                f"Current evaluation: {report}\n"
            ),
        )
        trace.append({"role": "optimization", "round": round_index, "output": optimization})
        move_errors = apply_relocations(spec, solution, optimization)
        report = _report_dict(spec, solution)
        report["move_errors"] = move_errors
        _keep(solution, report)
        critic = _ask(
            collector,
            backend,
            model,
            "critic",
            (
                "You are the Critic. The independent evaluator already decided feasibility.\n"
                "Assign the next repair to routing, charging, optimization, or architect.\n"
                '{"assign_to":"routing","fault":"...","instruction":"...","accept":false}\n'
                f"Evaluation: {report}\n"
            ),
        )
        trace.append({"role": "critic", "round": round_index, "output": critic})
        if report["feasible"]:
            break
        assigned = str(critic.get("assign_to") or "")
        expected = agent_for_fault(report.get("first_fault"))
        if assigned != expected:
            trace.append(
                {
                    "role": "controller",
                    "note": "critic assignment did not match the fault map",
                    "critic_assigned": assigned,
                    "assigned": expected,
                }
            )
            assigned = expected
        feedback = (
            f"fault={report.get('first_fault')} detail={report.get('fault_detail')} "
            f"routes={_route_ids(solution)} route_errors={route_errors} charge_errors={charge_errors} "
            f"owner={assigned}"
        )
        if assigned == "architect":
            break
        previous_fault = None if report.get("feasible") else str(report.get("first_fault") or "")
    if incumbent_report is not None and incumbent_report.get("feasible"):
        return incumbent_solution, incumbent_report, trace
    return latest_solution, latest_report, trace


def _generated_loop(
    spec: ProblemSpecV2,
    collector: UsageCollector,
    backend: Any,
    model: str,
    summary: dict[str, Any],
    feedback: str,
    trace: list[dict[str, Any]],
    max_rounds: int,
) -> tuple[SolutionV2 | None, dict[str, Any] | None, list[dict[str, Any]]]:
    incumbent_solution: SolutionV2 | None = None
    incumbent_report: dict[str, Any] | None = None
    latest_solution: SolutionV2 | None = None
    latest_report: dict[str, Any] | None = None
    instance = spec_payload(spec)
    contract = (
        "Write Python defining solve(instance: dict) -> dict. "
        "instance contains nodes, vehicles, requests, customer_ids, depot_ids, and native_objective. "
        "The summary may omit customers; the instance argument lists every customer_id. "
        "Return {'routes': [{'vehicle_type': '...', 'customers': ['id']}]}. "
        "Do not import evrptw_autolab, do not call a classical solver, and do not read files. "
        "Return JSON {\"code\": \"...\"}."
    )
    for round_index in range(max_rounds):
        routing = _ask(
            collector,
            backend,
            model,
            "routing",
            contract + f"\nRound {round_index}. Feedback: {feedback}\n" + json_summary(summary),
        )
        source = extract_python_source(str(routing.get("code") or routing.get("raw") or ""))
        trace.append({"role": "routing", "round": round_index, "generated": bool(source), "output_keys": list(routing)})
        executed = execute_generated_solver(source, instance)
        trace.append({"role": "executor", "round": round_index, "ok": executed["ok"], "errors": executed["errors"]})
        if not executed["ok"] or not isinstance(executed["routes"], dict):
            feedback = f"execution_error={executed['errors']}"
            critic = _ask(collector, backend, model, "critic", f"Execution failed. Assign a repair.\n{feedback}")
            trace.append({"role": "critic", "round": round_index, "output": critic})
            continue
        solution, route_errors = solution_from_plan(spec, executed["routes"])
        solution.metadata["attribution"] = "agent_generated_solver"
        report = _report_dict(spec, solution)
        report["route_errors"] = route_errors
        latest_solution = _snapshot(solution)
        latest_report = report
        if _better(report, incumbent_report):
            incumbent_solution = latest_solution
            incumbent_report = report
        charging = _ask(
            collector,
            backend,
            model,
            "charging",
            "Return station insertions for the generated routes, or an empty list.\n"
            '{"insertions":[]}\n'
            f"Evaluation: {report}",
        )
        trace.append({"role": "charging", "round": round_index, "output": charging})
        insert_charges(spec, solution, charging)
        report = _report_dict(spec, solution)
        latest_solution = _snapshot(solution)
        latest_report = report
        if _better(report, incumbent_report):
            incumbent_solution = latest_solution
            incumbent_report = report
        critic = _ask(
            collector,
            backend,
            model,
            "critic",
            f"Independent evaluation: {report}. Assign routing, charging, optimization, or architect.",
        )
        trace.append({"role": "critic", "round": round_index, "output": critic})
        if report["feasible"]:
            break
        feedback = f"fault={report.get('first_fault')} detail={report.get('fault_detail')}"
    optimization = _ask(
        collector,
        backend,
        model,
        "optimization",
        "Propose at most four relocations or an empty list. " '{"moves":[]}',
    )
    trace.append({"role": "optimization", "output": optimization})
    if incumbent_solution is not None:
        trial = _snapshot(incumbent_solution)
        apply_relocations(spec, trial, optimization)
        report = _report_dict(spec, trial)
        if _better(report, incumbent_report):
            incumbent_solution = trial
            incumbent_report = report
            latest_solution = trial
            latest_report = report
    if incumbent_report is not None and incumbent_report.get("feasible"):
        return incumbent_solution, incumbent_report, trace
    return latest_solution, latest_report, trace
