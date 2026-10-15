"""Classical non-LLM solver entry point."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

from evrptw_autolab.backbone.alns import alns_improve
from evrptw_autolab.backbone.charge_completion import complete_solution_charges
from evrptw_autolab.backbone.construct import construct_greedy
from evrptw_autolab.backbone.energy_repair import remove_redundant_stations, repair_energy
from evrptw_autolab.backbone.local_search import relocate_improve, two_opt_improve
from evrptw_autolab.backbone.util import candidate_vehicle_ids, clone_solution, evaluate, is_better
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2


def _reassign_vehicles(spec: ProblemSpecV2, solution: SolutionV2) -> SolutionV2:
    """Try cheaper vehicle types per route on heterogeneous fleets."""
    if not spec.capabilities.heterogeneous_fleet:
        return solution
    current = clone_solution(solution)
    current_report = evaluate(spec, current)
    for r_idx in range(len(current.routes)):
        best = current
        best_report = current_report
        for type_id in candidate_vehicle_ids(spec):
            trial = clone_solution(current)
            if r_idx < len(trial.vehicle_assignments):
                trial.vehicle_assignments[r_idx] = type_id
            else:
                trial.vehicle_assignments.append(type_id)
            trial.routes[r_idx] = [
                RouteStopV2(
                    node_id=stop.node_id,
                    vehicle_type_id=type_id,
                    event=stop.event,
                    charge_amount=stop.charge_amount,
                    charge_technology=stop.charge_technology,
                    target_soc=stop.target_soc,
                )
                for stop in trial.routes[r_idx]
            ]
            report = evaluate(spec, trial)
            if is_better(report, best_report):
                best = trial
                best_report = report
        current = best
        current_report = best_report
    return current


@dataclass
class ClassicalSolver:
    """Transparent constructive + energy-repair + ALNS baseline."""

    seed: int = 0
    time_limit_s: float = 5.0
    alns_iterations: int = 60
    use_alns: bool = True
    policy: object | None = None

    def solve(self, spec: ProblemSpecV2) -> SolutionV2:
        started = time.monotonic()
        rng = random.Random(int(self.seed))
        solution = construct_greedy(spec, rng, policy=self.policy)
        solution = repair_energy(spec, solution, policy=self.policy)
        solution = complete_solution_charges(spec, solution)
        solution = relocate_improve(spec, solution, max_passes=2)
        solution = two_opt_improve(spec, solution)
        solution = repair_energy(spec, solution, policy=self.policy)
        solution = complete_solution_charges(spec, solution)
        remaining = max(0.1, float(self.time_limit_s) - (time.monotonic() - started))
        if self.use_alns and remaining > 0.2:
            solution = alns_improve(
                spec,
                solution,
                rng,
                time_limit_s=remaining,
                iterations=self.alns_iterations,
                policy=self.policy,
            )
        solution = remove_redundant_stations(spec, solution)
        solution = complete_solution_charges(spec, solution)
        solution = _reassign_vehicles(spec, solution)
        report = evaluate(spec, solution)
        solution.metadata.update(
            {
                "solver": "classical_backbone",
                "seed": int(self.seed),
                "feasible": bool(report.feasible),
                "objective": report.objective,
                "objective_key": list(report.objective_key),
                "vehicles": report.vehicles,
                "distance": report.total_distance,
                "runtime_s": time.monotonic() - started,
                "first_fault": report.first_fault.as_dict() if report.first_fault else None,
            }
        )
        return solution


def solve_classical(
    spec: ProblemSpecV2,
    *,
    seed: int = 0,
    time_limit_s: float = 5.0,
    alns_iterations: int = 60,
    use_alns: bool = True,
    policy: object | None = None,
) -> SolutionV2:
    return ClassicalSolver(
        seed=seed,
        time_limit_s=time_limit_s,
        alns_iterations=alns_iterations,
        use_alns=use_alns,
        policy=policy,
    ).solve(spec)


def solve_report(
    spec: ProblemSpecV2,
    *,
    seed: int = 0,
    time_limit_s: float = 5.0,
) -> dict[str, Any]:
    sol = solve_classical(spec, seed=seed, time_limit_s=time_limit_s)
    report = evaluate(spec, sol)
    return {
        "feasible": report.feasible,
        "objective": report.objective,
        "vehicles": report.vehicles,
        "distance": report.total_distance,
        "violations": [v.as_dict() for v in report.violations[:20]],
        "metadata": sol.metadata,
        "routes": [[s.node_id for s in route] for route in sol.routes],
    }
