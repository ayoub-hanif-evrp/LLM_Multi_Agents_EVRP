"""Baselines and small typed-policy search helpers."""
from __future__ import annotations

import random
from collections.abc import Sequence

from .moves import Move
from .policy_dsl import Policy, evaluate, parse_policy

# All policies here MAXIMIZE score. Slack features are already "higher is safer" so they enter
# positively; every cost/detour/delta feature is negated so that shrinking it raises the score.
_CHARGING_POLICY: Policy = {"op": "neg", "arg": {"feature": "delta_charging_distance"}}
_TIME_POLICY: Policy = {"feature": "minimum_time_slack_after"}
_ENERGY_POLICY: Policy = {"feature": "minimum_energy_slack_after"}
_COMBINED_POLICY: Policy = {
    "op": "add",
    "args": [
        {"feature": "minimum_energy_slack_after"},
        {"feature": "minimum_time_slack_after"},
        {"op": "neg", "arg": {"feature": "delta_charging_distance"}},
        {"op": "neg", "arg": {"feature": "delta_distance_estimate"}},
        {"op": "neg", "arg": {"feature": "delta_charging_time"}},
        {"op": "neg", "arg": {"feature": "estimated_repair_cost"}},
    ],
}
# Reference DSL: same maximizing shape as "combined" (safer + cheaper), kept as a distinct,
# independently named baseline so experiments can compare a hand-tuned reference against it.
REFERENCE_DSL_POLICY: Policy = {
    "op": "add",
    "args": [
        {"feature": "minimum_energy_slack_after"},
        {"feature": "minimum_time_slack_after"},
        {"op": "neg", "arg": {"feature": "delta_charging_distance"}},
        {"op": "neg", "arg": {"feature": "delta_distance_estimate"}},
    ],
}

HANDCRAFTED_POLICIES: dict[str, Policy] = {
    "zero": {
        "op": "add",
        "args": [
            {"feature": "segment_customer_count"},
            {"op": "neg", "arg": {"feature": "segment_customer_count"}},
        ],
    },
    "charging": _CHARGING_POLICY,
    "charging-detour": _CHARGING_POLICY,
    "time": _TIME_POLICY,
    "low-time-slack": _TIME_POLICY,
    "energy": _ENERGY_POLICY,
    "low-energy-slack": _ENERGY_POLICY,
    "combined": _COMBINED_POLICY,
    "reference": REFERENCE_DSL_POLICY,
}
for _policy in HANDCRAFTED_POLICIES.values():
    parse_policy(_policy)


def random_typed_policy(rng: random.Random | None = None) -> Policy:
    rng = rng or random.Random()
    features = [
        "station_detour_contribution",
        "minimum_energy_slack_after",
        "minimum_time_slack_after",
        "delta_charging_time",
        "delta_distance_estimate",
    ]
    return parse_policy(
        {
            "op": "add",
            "args": [
                {"op": "mul", "args": [{"const": rng.uniform(-2, 2)}, {"feature": rng.choice(features)}]},
                {"op": "mul", "args": [{"const": rng.uniform(-2, 2)}, {"feature": rng.choice(features)}]},
            ],
        }
    )


def structured_mutation(policy: Policy, rng: random.Random | None = None) -> Policy:
    _ = rng
    return parse_policy(policy)


def select_move_by_policy(
    moves: Sequence[Move], features_list: Sequence[dict[str, float]], policy: Policy
) -> Move | None:
    if len(moves) != len(features_list):
        raise ValueError("moves and features_list must align")
    if not moves:
        return None
    return max(zip(moves, features_list, strict=True), key=lambda pair: evaluate(policy, pair[1]))[0]
