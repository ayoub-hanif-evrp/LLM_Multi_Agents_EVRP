"""Classical non-LLM solver entry point."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

from evrptw_autolab.backbone.alns import alns_improve
from evrptw_autolab.backbone.construct import construct_greedy
from evrptw_autolab.backbone.energy_repair import remove_redundant_stations, repair_energy
from evrptw_autolab.backbone.local_search import relocate_improve, two_opt_improve
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2


@dataclass
class ClassicalSolver:
    """Transparent constructive + energy-repair + ALNS baseline."""

    seed: int = 0
    time_limit_s: float = 5.0
    alns_iterations: int = 60
    use_alns: bool = True

    def solve(self, spec: ProblemSpecV2) -> SolutionV2:
        started = time.monotonic()
        rng = random.Random(int(self.seed))
        solution = construct_greedy(spec, rng)
        solution = repair_energy(spec, solution)
        solution = relocate_improve(spec, solution, max_passes=2)
        solution = two_opt_improve(spec, solution)
        solution = repair_energy(spec, solution)
        remaining = max(0.1, float(self.time_limit_s) - (time.monotonic() - started))
        if self.use_alns and remaining > 0.2:
            solution = alns_improve(
                spec,
                solution,
                rng,
                time_limit_s=remaining,
                iterations=self.alns_iterations,
            )
        solution = remove_redundant_stations(spec, solution)
        report = evaluate(spec, solution)
        solution.metadata.update(
            {
                "solver": "classical_backbone",
                "seed": int(self.seed),
                "feasible": bool(report.feasible),
                "objective": report.objective,
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
) -> SolutionV2:
    return ClassicalSolver(
        seed=seed,
        time_limit_s=time_limit_s,
        alns_iterations=alns_iterations,
        use_alns=use_alns,
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
