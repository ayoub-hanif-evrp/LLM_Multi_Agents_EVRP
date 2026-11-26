"""Shared experimental gate logic for research campaigns."""
from __future__ import annotations

from typing import Any


def paired_gate(
    outcomes: list[str],
    *,
    changed_decisions_total: int = 0,
    policy_origin: str = "unknown",
) -> dict[str, Any]:
    """Classify paired outcomes. Feasibility regressions outrank mixed/beneficial labels.

    A beneficial *handcrafted* result must not be reported as an LLM-discovery success.
    """
    wins = outcomes.count("improved")
    ties = outcomes.count("tie")
    obj_losses = outcomes.count("objective_regression")
    feas_losses = outcomes.count("feasibility_regression")
    losses = obj_losses + feas_losses
    missing = outcomes.count("missing") + outcomes.count("timeout") + outcomes.count("failed")
    both_infeasible = outcomes.count("both_infeasible")

    if feas_losses > 0:
        quality_gate = "feasibility_regression"
    elif missing > 0 and wins == 0 and losses == 0:
        quality_gate = "incomplete_panel"
    elif wins > 0 and losses == 0:
        quality_gate = "beneficial"
    elif wins > 0 and losses > 0:
        quality_gate = "mixed"
    elif losses > 0:
        quality_gate = "objective_regression"
    elif changed_decisions_total == 0 and all(o == "tie" for o in outcomes):
        quality_gate = "behaviorally_inert"
    else:
        quality_gate = "tie"

    llm_signal = "no_go"
    if policy_origin == "llm" and quality_gate == "beneficial":
        llm_signal = "go"
    elif policy_origin == "llm":
        llm_signal = "no_go"

    return {
        "feasibility_regressions": feas_losses,
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "objective_regressions": obj_losses,
        "missing_or_failed": missing,
        "both_infeasible": both_infeasible,
        "changed_decisions_total": int(changed_decisions_total),
        "quality_gate": quality_gate,
        "operator_activation": "active" if changed_decisions_total > 0 else "inactive",
        "search_space_signal": "go" if wins > 0 else "no_go",
        "llm_discovery_signal": llm_signal if policy_origin == "llm" else "not_applicable",
        "multi_agent_signal": "not_evaluated",
        "transfer_signal": "not_evaluated",
        "policy_origin": policy_origin,
    }
