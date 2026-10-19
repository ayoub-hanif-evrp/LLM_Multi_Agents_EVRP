"""Matched four-arm pilot protocol. This module does not call a model.

Search arms share the candidate-evaluation budget in ``fair_budget``.
Classical deployment is one solve per instance. A live Qwen run stays
unstarted until that budget is approved.
"""
from __future__ import annotations

from typing import Any

from evrptw_autolab.baselines.classical_pilot import PilotInstance
from evrptw_autolab.experiments.fair_budget import (
    ARMS,
    DECLARED_SELECTION_RULE,
    SEARCH_CANDIDATES,
    pilot_cost,
)
from evrptw_autolab.experiments.family_gate import gate_panel

STATUS = "not_started"


def pilot_protocol(panel: list[PilotInstance] | None = None) -> dict[str, Any]:
    rows = panel if panel is not None else gate_panel()
    cost = pilot_cost(rows)
    return {
        "status": STATUS,
        "model": "qwen3-coder:30b",
        "sequential_ollama": True,
        "arms": list(ARMS),
        "search_candidates": SEARCH_CANDIDATES,
        "selection_rule": DECLARED_SELECTION_RULE,
        "matched_fields": [
            "instances",
            "seed",
            "time_limit_s",
            "alns_iterations",
            "evaluator",
            "candidate_evaluations",
        ],
        "selection": DECLARED_SELECTION_RULE,
        "instances": [
            {
                "family": item.family,
                "instance_id": item.instance_id,
                "time_limit_s": item.time_limit_s,
                "alns_iterations": item.alns_iterations,
            }
            for item in rows
        ],
        "solver_passes": cost["solver_passes"],
        "solver_wall_s_lower_bound": cost["solver_wall_s_lower_bound"],
        "cost": cost,
        "reason": (
            "Live multi-agent evolution is not started. Search arms each receive "
            f"{SEARCH_CANDIDATES} candidate evaluations per instance on one seed. "
            "Classical receives one deployment evaluation. Token time is extra "
            "and is not measured in this protocol file."
        ),
    }
