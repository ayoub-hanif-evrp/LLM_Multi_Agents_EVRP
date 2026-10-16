"""Classical non-LLM solver entry point."""
from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass
from typing import Any

from evrptw_autolab.backbone.alns import alns_improve
from evrptw_autolab.backbone.charge_completion import complete_solution_charges
from evrptw_autolab.backbone.construct import construct_greedy
from evrptw_autolab.backbone.energy_repair import remove_redundant_stations, repair_energy
from evrptw_autolab.backbone.local_search import (
    merge_routes_improve,
    relocate_improve,
    two_opt_improve,
)
from evrptw_autolab.backbone.nonlinear_charge import optimize_solution_partial_charges
from evrptw_autolab.backbone.route_split import split_infeasible_routes
from evrptw_autolab.backbone.util import candidate_vehicle_ids, clone_solution, evaluate, is_better
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2


def _deadline_remaining(started: float, time_limit_s: float) -> float:
    return max(0.0, float(time_limit_s) - (time.monotonic() - started))


def _reassign_vehicles(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    deadline: float | None = None,
) -> SolutionV2:
    """Try cheaper vehicle types per route on heterogeneous fleets."""
    if not spec.capabilities.heterogeneous_fleet:
        return solution
    current = clone_solution(solution)
    current_report = evaluate(spec, current)
    for r_idx in range(len(current.routes)):
        if deadline is not None and time.monotonic() > deadline:
            break
        best = current
        best_report = current_report
        for type_id in candidate_vehicle_ids(spec):
            if deadline is not None and time.monotonic() > deadline:
                break
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


def repair_feasibility(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    policy: object | None = None,
    deadline: float | None = None,
) -> SolutionV2:
    """Unified repair: energy → charges → partial charge → route splits → local search."""
    current = clone_solution(solution)
    if deadline is not None and time.monotonic() > deadline:
        return current
    current = repair_energy(spec, current, policy=policy, deadline=deadline)
    current = complete_solution_charges(spec, current)
    current = optimize_solution_partial_charges(spec, current)
    report = evaluate(spec, current)
    if report.feasible:
        return current
    if deadline is not None and time.monotonic() > deadline:
        return current
    current = split_infeasible_routes(spec, current, policy=policy)
    current = optimize_solution_partial_charges(spec, current)
    if deadline is not None and time.monotonic() > deadline:
        return current
    current = relocate_improve(spec, current, max_passes=2, deadline=deadline)
    current = repair_energy(spec, current, policy=policy, deadline=deadline)
    current = complete_solution_charges(spec, current)
    current = optimize_solution_partial_charges(spec, current)
    return current


def _maybe_merge(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    deadline: float | None,
    max_passes: int = 2,
) -> SolutionV2:
    """Apply route merge only when the lexicographic objective improves."""
    if deadline is not None and time.monotonic() > deadline:
        return solution
    before = evaluate(spec, solution)
    merged = merge_routes_improve(spec, solution, max_passes=max_passes, deadline=deadline)
    after = evaluate(spec, merged)
    return merged if is_better(after, before) else solution


@dataclass
class ClassicalSolver:
    """Transparent constructive + energy-repair + ALNS baseline."""

    seed: int = 0
    time_limit_s: float = 5.0
    alns_iterations: int = 60
    use_alns: bool = True
    policy: object | None = None
    hard_timeout: bool = True

    def solve(self, spec: ProblemSpecV2) -> SolutionV2:
        if not self.hard_timeout:
            return self._solve_body(spec, box=None)
        box: dict[str, Any] = {"incumbent": None, "report": None, "spec": spec}
        # Grace lets cooperative deadline finish; hard cut only for true runaway work.
        grace = max(1.0, 0.15 * float(self.time_limit_s))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self._solve_body, spec, box)
            try:
                return future.result(timeout=float(self.time_limit_s) + grace)
            except FuturesTimeout:
                incumbent = box.get("incumbent")
                if isinstance(incumbent, SolutionV2):
                    out = clone_solution(incumbent)
                    out.metadata["deadline_exceeded"] = True
                    out.metadata["hard_timeout"] = True
                    out.metadata["runtime_s"] = float(self.time_limit_s) + grace
                    out.metadata.setdefault("solver", "classical_backbone")
                    out.metadata.setdefault("seed", int(self.seed))
                    out.metadata.setdefault("time_limit_s", float(self.time_limit_s))
                    return out
                rng = random.Random(int(self.seed))
                fallback = construct_greedy(spec, rng, policy=self.policy)
                fallback.metadata.update(
                    {
                        "solver": "classical_backbone",
                        "seed": int(self.seed),
                        "deadline_exceeded": True,
                        "hard_timeout": True,
                        "runtime_s": float(self.time_limit_s) + grace,
                        "time_limit_s": float(self.time_limit_s),
                    }
                )
                return fallback

    def _publish(
        self,
        box: dict[str, Any] | None,
        spec: ProblemSpecV2,
        solution: SolutionV2,
    ) -> None:
        if box is None:
            return
        report = evaluate(spec, solution)
        prev_report = box.get("report")
        if prev_report is None or is_better(report, prev_report):
            box["incumbent"] = clone_solution(solution)
            box["report"] = report

    def _solve_body(
        self,
        spec: ProblemSpecV2,
        box: dict[str, Any] | None,
    ) -> SolutionV2:
        started = time.monotonic()
        deadline = started + float(self.time_limit_s)
        rng = random.Random(int(self.seed))
        solution = construct_greedy(spec, rng, policy=self.policy)
        self._publish(box, spec, solution)
        solution = repair_feasibility(spec, solution, policy=self.policy, deadline=deadline)
        self._publish(box, spec, solution)
        if time.monotonic() < deadline:
            solution = two_opt_improve(spec, solution, deadline=deadline)
            self._publish(box, spec, solution)
        remaining = _deadline_remaining(started, self.time_limit_s)
        if self.use_alns and remaining > 0.2:
            solution = alns_improve(
                spec,
                solution,
                rng,
                time_limit_s=remaining,
                iterations=self.alns_iterations,
                policy=self.policy,
                deadline=deadline,
            )
            self._publish(box, spec, solution)
        if time.monotonic() < deadline:
            solution = _maybe_merge(spec, solution, deadline=deadline, max_passes=3)
            self._publish(box, spec, solution)
            # Always refresh charge annotations; keep only if not worse.
            polished = remove_redundant_stations(spec, solution)
            polished = complete_solution_charges(spec, polished)
            polished = optimize_solution_partial_charges(spec, polished)
            polished_report = evaluate(spec, polished)
            current_report = evaluate(spec, solution)
            if is_better(polished_report, current_report) or (
                polished_report.feasible == current_report.feasible
                and polished_report.objective_key == current_report.objective_key
            ):
                solution = polished
            elif not current_report.feasible and polished_report.feasible:
                solution = polished
            # Feasibility repair only if currently infeasible.
            if not evaluate(spec, solution).feasible:
                solution = repair_feasibility(spec, solution, policy=self.policy, deadline=deadline)
            else:
                # Feasible incumbents still need Bezzi charge completion after structural edits.
                solution = complete_solution_charges(spec, solution)
                solution = optimize_solution_partial_charges(spec, solution)
            solution = _reassign_vehicles(spec, solution, deadline=deadline)
            if time.monotonic() < deadline:
                solution = _maybe_merge(spec, solution, deadline=deadline, max_passes=2)
                solution = complete_solution_charges(spec, solution)
            self._publish(box, spec, solution)
        report = evaluate(spec, solution)
        elapsed = time.monotonic() - started
        solution.metadata.update(
            {
                "solver": "classical_backbone",
                "seed": int(self.seed),
                "feasible": bool(report.feasible),
                "objective": report.objective,
                "objective_key": list(report.objective_key),
                "vehicles": report.vehicles,
                "distance": report.total_distance,
                "runtime_s": elapsed,
                "time_limit_s": float(self.time_limit_s),
                "deadline_exceeded": elapsed > float(self.time_limit_s) + 0.05,
                "first_fault": report.first_fault.as_dict() if report.first_fault else None,
            }
        )
        self._publish(box, spec, solution)
        return solution


def solve_classical(
    spec: ProblemSpecV2,
    *,
    seed: int = 0,
    time_limit_s: float = 5.0,
    alns_iterations: int = 60,
    use_alns: bool = True,
    policy: object | None = None,
    hard_timeout: bool = True,
) -> SolutionV2:
    return ClassicalSolver(
        seed=seed,
        time_limit_s=time_limit_s,
        alns_iterations=alns_iterations,
        use_alns=use_alns,
        policy=policy,
        hard_timeout=hard_timeout,
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
