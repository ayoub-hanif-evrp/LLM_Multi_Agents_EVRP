"""Aggregate evaluation reports without hiding infeasibility."""
from __future__ import annotations

from statistics import mean, median

from evrptw_autolab.problem.types import EvaluationReport


def summarize(reports: list[EvaluationReport]) -> dict[str, float | int]:
    if not reports:
        return {"n": 0, "feasible_rate": 0.0, "crashes": 0, "timeouts": 0}
    feasible = [r for r in reports if r.feasible]
    return {
        "n": len(reports),
        "feasible_rate": len(feasible) / len(reports),
        "mean_vehicles": mean(r.vehicles for r in feasible) if feasible else mean(r.vehicles for r in reports),
        "mean_distance": mean(r.total_distance for r in feasible) if feasible else mean(r.total_distance for r in reports),
        "median_runtime_s": median(r.runtime_s for r in reports),
        "crashes": sum(1 for r in reports if r.crashed),
        "timeouts": sum(1 for r in reports if r.timed_out),
        "battery_violations": sum(r.battery_violations for r in reports),
        "time_window_violations": sum(r.time_window_violations for r in reports),
        "unserved": sum(len(r.unserved) for r in reports),
    }
