"""Declared candidate-evaluation budgets for the four-arm pilot.

Classical deployment is one solve per instance and seed. The three search
arms each receive the same number of candidate panel evaluations. This module
does not call a model and does not tune the selection rule on held-out data.
"""
from __future__ import annotations

from typing import Any

from evrptw_autolab.baselines.classical_pilot import PilotInstance
from evrptw_autolab.experiments.family_gate import gate_panel

SEARCH_CANDIDATES = 4
DECLARED_SELECTION_RULE = "conservative"
# Recorded means from campaign_20261017T163126Z. They scale a future pilot.
# They are not a measurement of that pilot.
RECORDED_SINGLE_AGENT_TOKENS_PER_CALL = 686
RECORDED_FIVE_AGENT_TOKENS_PER_CALL = 1470
ARMS = ("classical", "random_evolution", "single_agent", "five_agent")


def solver_passes(n_instances: int, *, candidates: int = SEARCH_CANDIDATES) -> dict[str, int]:
    """Panel evaluations, one seed. Search arms match. Classical is one deployment."""
    instances = max(0, int(n_instances))
    search = instances * int(candidates)
    return {
        "classical": instances,
        "random_evolution": search,
        "single_agent": search,
        "five_agent": search,
    }


def pilot_cost(panel: list[PilotInstance] | None = None) -> dict[str, Any]:
    """Solver-time lower bound and a token extrapolation. LLM wall time is not measured."""
    rows = panel if panel is not None else gate_panel()
    per_pass_s = sum(float(item.time_limit_s) for item in rows)
    passes = solver_passes(len(rows))
    solver_s = per_pass_s * sum(passes.values()) / max(len(rows), 1)
    single_tokens = SEARCH_CANDIDATES * RECORDED_SINGLE_AGENT_TOKENS_PER_CALL
    five_tokens = SEARCH_CANDIDATES * RECORDED_FIVE_AGENT_TOKENS_PER_CALL
    return {
        "instances": len(rows),
        "search_candidates": SEARCH_CANDIDATES,
        "selection_rule": DECLARED_SELECTION_RULE,
        "solver_passes": passes,
        "solver_wall_s_lower_bound": solver_s,
        "solver_wall_hours_lower_bound": solver_s / 3600.0,
        "llm_calls_lower_bound": {
            "classical": 0,
            "random_evolution": 0,
            "single_agent": SEARCH_CANDIDATES,
            "five_agent": SEARCH_CANDIDATES * 4,
        },
        "token_extrapolation": {
            "basis": "campaign_20261017T163126Z mean tokens per recorded instance call",
            "single_agent": single_tokens,
            "five_agent": five_tokens,
            "random_evolution": 0,
            "total": single_tokens + five_tokens,
            "measured": False,
        },
        "approval_required": True,
        "note": (
            "Solver seconds assume every evaluation uses its full time limit on one seed. "
            "Token figures extrapolate an earlier campaign and are not a Qwen measurement. "
            "LLM wall-clock time is additional and is not estimated here."
        ),
    }
