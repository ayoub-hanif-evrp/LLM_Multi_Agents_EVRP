"""Matched four-arm pilot protocol. This module does not call a model.

Arms share instances, seed, time limit, ALNS iteration cap, and the trusted
evaluator. Selection is feasibility first, then the lexicographic objective.
A live Qwen run stays unstarted until the development gate and the charging
ablation are on record and a wall-clock budget is approved.
"""
from __future__ import annotations

from typing import Any

from evrptw_autolab.baselines.classical_pilot import PilotInstance
from evrptw_autolab.experiments.family_gate import gate_panel

ARMS = ("classical", "random_evolution", "single_agent", "five_agent")
MODEL = "qwen3-coder:30b"
RANDOM_EXPRESSIONS = 4
STATUS = "not_started"


def pilot_protocol(panel: list[PilotInstance] | None = None) -> dict[str, Any]:
    rows = panel if panel is not None else gate_panel()
    per_pass_s = sum(float(item.time_limit_s) for item in rows)
    solves = {
        "classical": len(rows),
        "random_evolution": len(rows) * RANDOM_EXPRESSIONS,
        "single_agent": len(rows),
        "five_agent": len(rows),
    }
    return {
        "status": STATUS,
        "model": MODEL,
        "sequential_ollama": True,
        "arms": list(ARMS),
        "matched_fields": [
            "instances",
            "seed",
            "time_limit_s",
            "alns_iterations",
            "evaluator",
        ],
        "selection": "feasibility_first_then_lexicographic_objective",
        "instances": [
            {
                "family": item.family,
                "instance_id": item.instance_id,
                "time_limit_s": item.time_limit_s,
                "alns_iterations": item.alns_iterations,
            }
            for item in rows
        ],
        "solver_passes": solves,
        "solver_wall_s_lower_bound": per_pass_s * sum(solves.values()) / max(len(rows), 1),
        "reason": (
            "Live multi-agent evolution is not started. The lower bound counts "
            "solver time only, on one seed, with four random-evolution expressions "
            "and one generation of each LLM arm. Token time is extra."
        ),
    }
