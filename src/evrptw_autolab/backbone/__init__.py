"""Human-authored classical optimization backbone (Track 2 scaffolding).

LLM agents may later replace scoring/policy components; this package itself
contains no LLM calls. All feasibility is decided by ``evaluate_solution_v2``.
"""

from evrptw_autolab.backbone.solver import ClassicalSolver, solve_classical

__all__ = ["ClassicalSolver", "solve_classical"]
