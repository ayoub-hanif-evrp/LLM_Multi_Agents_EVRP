"""Lexicographic scientific objective: feasibility, then vehicles, then distance."""
from __future__ import annotations

from evrptw_autolab.problem.types import EvaluationReport


def lex_key(report: EvaluationReport) -> tuple[int, int, float]:
    infeas = 0 if report.feasible else 1
    return (infeas, report.vehicles, report.total_distance)
