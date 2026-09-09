"""Generated-solver interface expected by the sandbox driver."""
from __future__ import annotations

SOLVE_SIGNATURE = "def solve(instance, seed: int, time_limit_s: float)"
ALLOWED_RUNTIME_IMPORTS = (
    "evrptw_autolab.problem",
    "evrptw_autolab.problem.physics",
    "evrptw_autolab.problem.types",
    "evrptw_autolab.problem.schneider",
)
