"""The bundle rule rejects a one-seed win and a feasibility regression."""
from __future__ import annotations

import random

from evrptw_autolab.components.expressions import wrap_expression
from evrptw_autolab.experiments.bundle_selection import (
    RANDOM_DISCOVERY_SEED,
    conservative_decision,
    random_removal_expression,
)


def _pair(outcome: str, *, baseline_feasible: bool = True, candidate_feasible: bool = True) -> dict:
    return {
        "baseline_feasible": baseline_feasible,
        "candidate_feasible": candidate_feasible,
        "paired_outcome": outcome,
    }


def test_one_seed_win_with_later_losses_is_rejected() -> None:
    decision = conservative_decision(
        [_pair("candidate"), _pair("baseline"), _pair("baseline")]
    )
    assert decision["accepted"] is False
    assert decision["reason"] == "objective_regression"
    assert decision["wins"] == 1
    assert decision["losses"] == 2


def test_uniform_tie_is_not_an_improvement() -> None:
    decision = conservative_decision([_pair("tie"), _pair("tie")])
    assert decision["accepted"] is False
    assert decision["reason"] == "no_strict_improvement"


def test_no_regression_with_one_strict_gain_is_accepted() -> None:
    decision = conservative_decision([_pair("candidate"), _pair("tie")])
    assert decision["accepted"] is True
    assert decision["reason"] == "accepted_no_regression"


def test_lower_infeasible_duration_is_a_feasibility_regression() -> None:
    decision = conservative_decision(
        [_pair("baseline", baseline_feasible=True, candidate_feasible=False)]
    )
    assert decision["accepted"] is False
    assert decision["reason"] == "feasibility_regression"


def test_random_removal_expressions_are_reproducible_and_valid() -> None:
    first = [random_removal_expression(random.Random(RANDOM_DISCOVERY_SEED)) for _ in range(4)]
    second = [random_removal_expression(random.Random(RANDOM_DISCOVERY_SEED)) for _ in range(4)]
    assert first == second
    for expression in first:
        source = wrap_expression("removal_priority", expression)
        assert "def removal_priority" in source
        assert "import" not in source
