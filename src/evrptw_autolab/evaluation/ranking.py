"""Parent vs child ranking under identical instances/seeds/limits."""
from __future__ import annotations

from evrptw_autolab.problem.types import EvaluationReport


def rank_key(report: EvaluationReport) -> tuple[int, int, int, int, float]:
    crash = 0 if report.parse_ok and not report.crashed and not report.timed_out else 1
    infeas = 0 if report.feasible else 1
    violations = (
        len(report.unserved)
        + len(report.duplicates)
        + report.capacity_violations
        + report.time_window_violations
        + report.battery_violations
        + report.charging_violations
        + report.depot_violations
    )
    return (crash, infeas, violations, report.vehicles, report.total_distance)


def child_is_better(parent: EvaluationReport, child: EvaluationReport) -> bool:
    return rank_key(child) < rank_key(parent)


def panel_rank_key(reports: list[EvaluationReport]) -> tuple[int, int, int, float]:
    """Aggregate key: crashes, infeasible count, total vehicles, total distance."""
    crashes = sum(1 for r in reports if r.crashed or not r.parse_ok or r.timed_out)
    infeas = sum(1 for r in reports if not r.feasible)
    vehicles = sum(int(r.vehicles or 0) for r in reports if r.feasible)
    distance = sum(float(r.total_distance or 0.0) for r in reports if r.feasible)
    return (crashes, infeas, vehicles, distance)


def panel_is_better(parent: list[EvaluationReport], child: list[EvaluationReport]) -> bool:
    return panel_rank_key(child) < panel_rank_key(parent)
