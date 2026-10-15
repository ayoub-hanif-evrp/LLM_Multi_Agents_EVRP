"""Population-based multi-agent component evolution (CV-MAPE)."""

from evrptw_autolab.components.evolution.engine import (
    EvolutionConfig,
    evaluate_candidate_on_panel,
    run_evolution,
)
from evrptw_autolab.components.evolution.fitness import compare_panel, panel_is_better

__all__ = [
    "EvolutionConfig",
    "evaluate_candidate_on_panel",
    "run_evolution",
    "compare_panel",
    "panel_is_better",
]
