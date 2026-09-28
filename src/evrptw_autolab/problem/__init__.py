"""Canonical EVRPTW problem mathematics. This package is not a solver."""

from evrptw_autolab.problem.evaluator import evaluate_solution, first_fault
from evrptw_autolab.problem.hashes import instance_hashes, write_instance_hashes
from evrptw_autolab.problem.objective import lex_key
from evrptw_autolab.problem.physics import (
    distance,
    energy_required,
    full_recharge,
    propagate_route,
    travel_time,
)
from evrptw_autolab.problem.private import perturb_instance, private_set, smoke_instance
from evrptw_autolab.problem.schneider import discover_instances, load_instance, parse_solomon
from evrptw_autolab.problem.types import (
    CandidateSolution,
    EvaluationReport,
    EVRPTWInstance,
    Node,
    VehicleSpec,
)

__all__ = [
    "CandidateSolution",
    "EVRPTWInstance",
    "EvaluationReport",
    "Node",
    "VehicleSpec",
    "discover_instances",
    "distance",
    "energy_required",
    "evaluate_solution",
    "first_fault",
    "full_recharge",
    "instance_hashes",
    "lex_key",
    "load_instance",
    "parse_solomon",
    "perturb_instance",
    "private_set",
    "propagate_route",
    "smoke_instance",
    "travel_time",
    "write_instance_hashes",
]
