"""Counterexample challenge catalogue: normalizer reuse, metamorphic invariances, and the
concrete revision evidence a synthesizer/critic loop needs when a policy fails a challenge."""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from chargecegis.construction import construct_initial_solution
from chargecegis.counterexamples import ChallengeType, _score, execute_challenge
from chargecegis.data import load_instance
from chargecegis.features import FEATURE_NAMES, FeatureNormalizer
from chargecegis.search import HANDCRAFTED_POLICIES

ROOT = Path(__file__).resolve().parents[1]
SCHNEIDER = ROOT / "dataset" / "schneider" / "raw_instances"


@pytest.fixture(scope="module")
def small_instance():
    return load_instance(SCHNEIDER / "c101C5.txt")


@pytest.fixture(scope="module")
def small_solution(small_instance):
    return construct_initial_solution(small_instance).solution


def test_score_helper_applies_normalizer_before_evaluating_policy() -> None:
    """Every challenge routes scoring through this helper; it must reproduce ALNS's
    normalize-then-evaluate contract exactly, not evaluate raw features when a normalizer is given."""
    policy = {"feature": "minimum_time_slack_after"}
    raw_features = {"minimum_time_slack_after": 100.0}
    normalizer = FeatureNormalizer(
        means=dict.fromkeys(FEATURE_NAMES, 0.0),
        scales=dict.fromkeys(FEATURE_NAMES, 1.0),
        constant=dict.fromkeys(FEATURE_NAMES, False),
    )
    assert _score(policy, raw_features, None) == 100.0
    assert _score(policy, raw_features, normalizer) == normalizer.clip_bound  # z=100 clipped to 5.0


@pytest.mark.parametrize(
    "challenge_type", [ChallengeType.CUSTOMER_RELABEL, ChallengeType.STATION_RELABEL]
)
def test_relabel_challenges_preserve_move_ranking(challenge_type, small_instance, small_solution) -> None:
    """A policy built only from geometry/schedule features must rank moves identically whether
    customers or stations carry their original ids or a shuffled set of ids."""
    policy = HANDCRAFTED_POLICIES["combined"]
    result = execute_challenge(challenge_type.value, policy, small_instance, small_solution, random.Random(0))
    assert result["applicable"]
    assert result["passed"]
    assert result["details"]["paired_moves"] > 0
    assert result["details"]["max_abs_score_diff"] < 1e-9


def test_move_order_challenge_selects_same_move_regardless_of_pool_order(small_instance, small_solution) -> None:
    policy = HANDCRAFTED_POLICIES["combined"]
    result = execute_challenge(ChallengeType.MOVE_ORDER.value, policy, small_instance, small_solution, random.Random(0))
    assert result["applicable"]
    assert result["passed"]
    assert result["details"]["order_changed"]


@pytest.mark.parametrize(
    "policy_name, expect_sensitive",
    [("charging", True), ("zero", False)],
)
def test_charging_feature_perturbation_detects_charging_sensitivity(
    policy_name, expect_sensitive, small_instance, small_solution
) -> None:
    """A policy that reads charging features must be flagged sensitive; a policy that ignores
    every feature (``zero``) must be flagged insensitive -- either way as ``expect_sensitive`` predicts."""
    policy = HANDCRAFTED_POLICIES[policy_name]
    result = execute_challenge(
        ChallengeType.CHARGING_FEATURE_PERTURBATION.value, policy, small_instance, small_solution,
        random.Random(0), expect_sensitive=expect_sensitive,
    )
    assert result["applicable"]
    assert result["passed"]


def test_handcrafted_equivalence_challenge_gives_revision_evidence_for_trivial_policy(
    small_instance, small_solution
) -> None:
    """A policy that is literally a handcrafted baseline is degenerate research-wise: the
    challenge must fail *and* the details must name which baseline it collapses to, since that
    is exactly the evidence a synthesizer/critic revision loop needs to act on."""
    trivial_policy = HANDCRAFTED_POLICIES["charging"]
    result = execute_challenge(
        ChallengeType.HANDCRAFTED_EQUIVALENCE.value, trivial_policy, small_instance, small_solution, random.Random(0)
    )
    assert result["applicable"]
    assert not result["passed"]
    assert result["details"]["matches_handcrafted"] in {"charging", "charging-detour"}
