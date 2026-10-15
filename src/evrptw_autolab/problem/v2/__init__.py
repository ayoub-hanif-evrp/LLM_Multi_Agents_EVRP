"""VoltForge 2.0 general EVRP representation and independent evaluator."""

from evrptw_autolab.problem.v2.evaluator import evaluate_solution_v2
from evrptw_autolab.problem.v2.report import EvaluationReportV2, StopStateV2, ViolationV2
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    ProblemFamily,
    ProblemSpecV2,
    RouteStopV2,
    SolutionV2,
)

__all__ = [
    "CapabilityFlags",
    "EvaluationReportV2",
    "ProblemFamily",
    "ProblemSpecV2",
    "RouteStopV2",
    "SolutionV2",
    "StopStateV2",
    "ViolationV2",
    "evaluate_solution_v2",
]
