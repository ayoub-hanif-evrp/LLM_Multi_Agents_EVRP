"""One-component ablations against a default policy bundle.

A different expression, a different route, and a better feasible objective are
recorded separately. Infeasible objectives never outrank a feasible baseline.
"""
from __future__ import annotations

from typing import Any

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.components.interfaces import ComponentKind
from evrptw_autolab.components.loader import load_bundle
from evrptw_autolab.problem.v2.types import ProblemSpecV2

KINDS: tuple[ComponentKind, ...] = ("insertion_score", "station_score", "removal_priority")


def paired_feasible_outcome(
    baseline_feasible: bool,
    baseline_key: tuple[float, ...],
    candidate_feasible: bool,
    candidate_key: tuple[float, ...],
) -> str:
    """Return baseline, candidate, or tie. Feasibility outranks every objective."""
    if baseline_feasible and not candidate_feasible:
        return "baseline"
    if candidate_feasible and not baseline_feasible:
        return "candidate"
    if not baseline_feasible and not candidate_feasible:
        return "tie_infeasible"
    if candidate_key < baseline_key:
        return "candidate"
    if baseline_key < candidate_key:
        return "baseline"
    return "tie"


def ablate_components(
    spec: ProblemSpecV2,
    variants: dict[str, dict[ComponentKind, str]],
    *,
    seed: int,
    time_limit_s: float,
    alns_iterations: int = 40,
    hard_timeout: bool = True,
) -> list[dict[str, Any]]:
    """Solve one variant at a time. The first variant is the paired baseline."""
    rows: list[dict[str, Any]] = []
    baseline_routes: list[list[str]] | None = None
    baseline_feasible = False
    baseline_key: tuple[float, ...] = ()
    for name, sources in variants.items():
        bundle, errors = load_bundle({kind: sources[kind] for kind in KINDS})
        solution = solve_classical(
            spec,
            seed=seed,
            time_limit_s=time_limit_s,
            alns_iterations=alns_iterations,
            policy=bundle,
            hard_timeout=hard_timeout,
        )
        report = evaluate(spec, solution)
        routes = [[stop.node_id for stop in route] for route in solution.routes]
        key = tuple(float(v) for v in report.objective_key)
        if baseline_routes is None:
            baseline_routes = routes
            baseline_feasible = bool(report.feasible)
            baseline_key = key
            outcome = "baseline"
        else:
            outcome = paired_feasible_outcome(baseline_feasible, baseline_key, bool(report.feasible), key)
        rows.append(
            {
                "variant": name,
                "seed": seed,
                "time_limit_s": time_limit_s,
                "load_errors": errors,
                "feasible": bool(report.feasible),
                "objective_key": list(key),
                "vehicles": report.vehicles,
                "distance": report.total_distance,
                "duration": report.total_duration,
                "first_fault": (
                    f"{report.first_fault.family}: {report.first_fault.detail}" if report.first_fault else ""
                ),
                "routes": routes,
                "route_changed": routes != baseline_routes,
                "paired_outcome": outcome,
                "objective_components": dict(report.objective_components),
                "charging_visits": report.charging_visits,
                "unserved": list(report.unserved),
                "violations": [item.as_dict() for item in report.violations],
                "trajectories": [
                    [
                        {
                            "node_id": state.node_id,
                            "arrival_time": state.arrival_time,
                            "departure_time": state.departure_time,
                            "battery_arrival": state.battery_arrival,
                            "battery_departure": state.battery_departure,
                            "energy_charged": state.energy_charged,
                            "charge_technology": state.charge_technology,
                        }
                        for state in route
                    ]
                    for route in report.trajectories
                ],
                "scorer_calls": dict(solution.metadata.get("scorer_calls") or {}),
                "completed_within_budget": solution.metadata.get("completed_within_budget"),
                "worker_wait_s": solution.metadata.get("worker_wait_s"),
                "wall_clock_s": solution.metadata.get("wall_clock_s"),
                "budget_overrun": solution.metadata.get("budget_overrun"),
                "solution_feasible": solution.metadata.get("solution_feasible"),
                "parent_validated": solution.metadata.get("parent_validated"),
            }
        )
    return rows
