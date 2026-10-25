"""Named classical operators the controller is allowed to select."""

from __future__ import annotations

import random

from evrptw_autolab.discovery.policy_language import PolicyError, choose_minimum
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2
from evrptw_autolab.transfer.context_features import search_context
from evrptw_autolab.transfer.selective_controller import select_operator

DESTROY_REFERENCES = {"destroy_random": "random", "destroy_worst": "worst"}


def choose_destroy(
    spec: ProblemSpecV2,
    operator: OperatorSpec,
    solution: SolutionV2,
    rng: random.Random,
    weights: dict[str, float],
) -> tuple[str, str]:
    """Return the destroy name and the controller action."""
    selection = select_operator(
        operator,
        spec.capabilities,
        search_context(spec, solution),
        rule=operator.applicability_rule,
    )
    mapped = DESTROY_REFERENCES.get(operator.implementation_reference)
    if selection.action != "apply" or mapped is None:
        return _roulette(rng, weights), selection.action if mapped is not None else "abstain"
    return mapped, selection.action


def choose_station_id(
    spec: ProblemSpecV2,
    operator: OperatorSpec,
    rows: list[tuple[str, dict[str, float]]],
    context: dict[str, float],
) -> tuple[str, str, str]:
    """Pick a feasible station. The classical choice is the shorter detour."""
    if not rows:
        raise ValueError("no feasible stations")
    classical = min(rows, key=lambda row: (row[1]["detour"], row[0]))
    selection = select_operator(operator, spec.capabilities, context, rule=operator.applicability_rule)
    chosen = classical
    if selection.action == "apply" and operator.candidate_scoring_policy:
        try:
            index = choose_minimum(operator.candidate_scoring_policy, [row[1] for row in rows])
        except PolicyError:
            selection_action = "abstain"
            return classical[0], classical[0], selection_action
        else:
            chosen = rows[index]
    return chosen[0], classical[0], selection.action


def _roulette(rng: random.Random, weights: dict[str, float]) -> str:
    total = sum(weights.values()) or 1.0
    pick = rng.random() * total
    acc = 0.0
    chosen = "random"
    for name, weight in weights.items():
        acc += weight
        if pick <= acc:
            chosen = name
            break
    return chosen
