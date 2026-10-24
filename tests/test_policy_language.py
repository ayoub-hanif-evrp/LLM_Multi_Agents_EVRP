"""Generated scores stay inside the restricted language."""

import pytest

from evrptw_autolab.discovery.policy_language import PolicyError, choose_minimum, evaluate_policy


def test_arithmetic_uses_only_declared_features() -> None:
    score = evaluate_policy("delta_distance + 0.5 * incremental_energy_cost", {"delta_distance": 2.0, "incremental_energy_cost": 4.0})
    assert score == 4.0


def test_energy_score_selects_a_different_row_from_distance() -> None:
    rows = (
        {"delta_distance": 1.172, "incremental_energy_cost": 11.715728752538098},
        {"delta_distance": 4.0, "incremental_energy_cost": 0.4},
    )
    assert choose_minimum("delta_distance", rows) == 0
    assert choose_minimum("incremental_energy_cost", rows) == 1


def test_import_attribute_and_unknown_feature_are_rejected() -> None:
    with pytest.raises(PolicyError):
        evaluate_policy("__import__('os')", {})
    with pytest.raises(PolicyError):
        evaluate_policy("battery_margin.bit_length()", {"battery_margin": 1.0})
    with pytest.raises(PolicyError):
        evaluate_policy("instance_id", {})
    with pytest.raises(PolicyError):
        evaluate_policy("1 / 0", {})


def test_non_finite_results_are_rejected() -> None:
    with pytest.raises(PolicyError):
        evaluate_policy("delta_distance / 0.0", {"delta_distance": 1.0})
