"""Deterministic charging repair for a fixed customer sequence.

This is not ALNS and it is not an LLM decision. Callers must keep that
attribution on the solution metadata.
"""
from __future__ import annotations

from evrptw_autolab.backbone.charge_completion import (
    complete_solution_charges,
    route_needs_charge_completion,
)
from evrptw_autolab.problem.v2.evaluator import evaluate_solution_v2
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2


def complete_missing_charges(spec: ProblemSpecV2, solution: SolutionV2) -> tuple[SolutionV2, str]:
    """Fill Bezzi charge amounts with the existing recharge DP when the agent omitted them."""
    if not spec.capabilities.multiple_charge_technologies:
        solution.metadata["charging"] = "not_required"
        return solution, "not_required"
    if not any(route_needs_charge_completion(spec, route) for route in solution.routes):
        solution.metadata["charging"] = "agent_explicit"
        solution.metadata["classical_alns"] = False
        return solution, "agent_explicit"
    planned = complete_solution_charges(spec, solution, drop_idle_stations=True)
    planned.metadata["method"] = "agentic_v2"
    planned.metadata["charging"] = "deterministic_bezzi_recharge_dp"
    planned.metadata["attribution"] = "agentic_customer_plan_with_deterministic_charge_repair"
    planned.metadata["classical_alns"] = False
    return planned, "deterministic_bezzi_recharge_dp"


def certify_charging(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    insert_stations: bool = False,
) -> tuple[SolutionV2, str]:
    """Complete explicit charge plans. Station insertion is optional and labeled."""
    solution, mode = complete_missing_charges(spec, solution)
    if not insert_stations or not spec.capabilities.battery:
        return solution, mode
    report = evaluate_solution_v2(spec, solution)
    if report.feasible or not any(item.family in {"BATTERY", "CHARGE_POLICY"} for item in report.violations):
        return solution, mode
    from evrptw_autolab.backbone.energy_repair import repair_energy

    repaired = repair_energy(spec, solution, max_inserts=8)
    repaired.metadata["method"] = "agentic_v2"
    repaired.metadata["charging"] = "deterministic_energy_repair"
    repaired.metadata["attribution"] = "agentic_customer_plan_with_deterministic_charge_repair"
    repaired.metadata["classical_alns"] = False
    return repaired, "deterministic_energy_repair"
