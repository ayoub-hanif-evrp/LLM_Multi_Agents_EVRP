"""Fitness for evolved component bundles."""
from __future__ import annotations

from evrptw_autolab.problem.v2.report import EvaluationReportV2


def fitness_from_report(report: EvaluationReportV2, runtime_s: float) -> float:
    """Higher is better: feasibility first, then negated objective key, then speed."""
    if not report.feasible:
        viol = len(report.violations) + sum(float(v.magnitude or 0.0) for v in report.violations)
        return -1_000_000.0 - 100.0 * viol - runtime_s
    score = 1_000_000.0
    if report.objective_key:
        scale = 1.0
        for value in report.objective_key:
            score -= float(value) * scale
            scale *= 1e-3
    elif report.objective is not None:
        score -= float(report.objective)
    score -= 0.01 * runtime_s
    return score
