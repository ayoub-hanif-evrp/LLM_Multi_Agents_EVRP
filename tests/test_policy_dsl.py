"""Policy DSL type-checking, the handcrafted time-ranking sign convention, and normalizer
constant/clip behavior used by both ALNS ranking and counterexample scoring."""
from __future__ import annotations

import pytest

from chargecegis.features import FEATURE_NAMES, FeatureNormalizer
from chargecegis.policy_dsl import evaluate, validate_policy
from chargecegis.search import HANDCRAFTED_POLICIES

_INVALID_TYPED_ASTS = [
    pytest.param(
        {"op": "lt", "left": {"feature": "delta_distance_estimate"}, "right": {"const": 1.0}},
        "must evaluate to NUMBER",
        id="root_must_be_number_not_boolean",
    ),
    pytest.param(
        {"op": "add", "args": [
            {"feature": "delta_distance_estimate"},
            {"op": "lt", "left": {"const": 1.0}, "right": {"const": 2.0}},
        ]},
        "requires NUMBER operands",
        id="arithmetic_op_rejects_boolean_operand",
    ),
    pytest.param(
        {"op": "if", "condition": {"feature": "delta_distance_estimate"},
         "then": {"const": 1.0}, "else": {"const": 2.0}},
        "condition must be BOOLEAN",
        id="if_condition_must_be_boolean",
    ),
    pytest.param(
        {"op": "if",
         "condition": {"op": "lt", "left": {"const": 1.0}, "right": {"const": 2.0}},
         "then": {"op": "lt", "left": {"const": 1.0}, "right": {"const": 2.0}},
         "else": {"const": 2.0}},
        "branches must be NUMBER",
        id="if_branches_must_be_number",
    ),
]


def test_handcrafted_time_policy_scores_higher_slack_as_safer() -> None:
    """Slack features are "higher is safer": a route with more remaining time slack after a move
    must score at least as high as an otherwise-identical, tighter one -- never the reverse."""
    policy = HANDCRAFTED_POLICIES["time"]
    safer = {"minimum_time_slack_after": 50.0}
    riskier = {"minimum_time_slack_after": 5.0}
    assert evaluate(policy, safer) > evaluate(policy, riskier)


def test_unknown_feature_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown feature"):
        validate_policy({"feature": "not_a_real_feature_name"})


@pytest.mark.parametrize("ast, message", _INVALID_TYPED_ASTS)
def test_type_checking_rejects_boolean_number_mismatches(ast: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_policy(ast)


def test_policy_must_use_at_least_one_feature() -> None:
    with pytest.raises(ValueError, match="does not use a feature"):
        validate_policy({"const": 1.0})


def test_normalizer_marks_near_constant_features_zero_and_clips_extremes() -> None:
    vectors = []
    for i in range(10):
        vector = dict.fromkeys(FEATURE_NAMES, 0.0)
        vector["delta_distance_estimate"] = 5.0  # identical across the whole fit sample
        vector["minimum_energy_slack_after"] = float(i)  # genuinely varies
        vectors.append(vector)
    normalizer = FeatureNormalizer().fit_balanced(vectors)

    assert normalizer.constant["delta_distance_estimate"] is True
    assert normalizer.constant["minimum_energy_slack_after"] is False

    transformed = normalizer.transform(
        {"delta_distance_estimate": 999.0, "minimum_energy_slack_after": 999.0}
    )
    assert transformed["delta_distance_estimate"] == 0.0
    assert transformed["minimum_energy_slack_after"] == normalizer.clip_bound
