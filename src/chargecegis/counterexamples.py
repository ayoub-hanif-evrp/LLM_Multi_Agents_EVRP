"""Executable metamorphic checks and the deterministic challenge catalogue."""
from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import replace
from enum import StrEnum
from typing import Any

from .alns import remove_empty_routes
from .construction import insert_customers_best_fit
from .features import FeatureNormalizer, compute_features, compute_features_for_solutions
from .moves import (
    Move,
    MoveType,
    RemovalUnit,
    apply_move,
    enumerate_moves,
    enumerate_removal_units,
    sample_candidate_pool,
)
from .policy_dsl import Policy, evaluate
from .problem import Instance, Route, Solution
from .propagation import propagate_route
from .search import HANDCRAFTED_POLICIES, select_move_by_policy


def _score(policy: Policy, features: dict[str, float], normalizer: FeatureNormalizer | None) -> float:
    """Score a raw feature vector, applying ``normalizer`` first when given -- the same
    normalize-then-evaluate contract :mod:`chargecegis.alns` uses for equal-budget ranking, so
    counterexample checks exercise policies exactly as the solver does."""
    if normalizer is not None:
        features = normalizer.transform(features)
    return evaluate(policy, features)


class ChallengeType(StrEnum):
    CUSTOMER_RELABEL = "CUSTOMER_RELABEL"
    STATION_RELABEL = "STATION_RELABEL"
    ROUTE_ORDER = "ROUTE_ORDER"
    MOVE_ORDER = "MOVE_ORDER"
    NO_FEASIBLE_STATION = "NO_FEASIBLE_STATION"
    TIGHT_DEPOT_HORIZON = "TIGHT_DEPOT_HORIZON"
    FLEET_INCREASE = "FLEET_INCREASE"
    DOWNSTREAM_LATENESS = "DOWNSTREAM_LATENESS"
    CHARGING_FEATURE_PERTURBATION = "CHARGING_FEATURE_PERTURBATION"
    HANDCRAFTED_EQUIVALENCE = "HANDCRAFTED_EQUIVALENCE"


# --- relabeling / permutation primitives ------------------------------------

def _relabel(instance: Instance, solution: Solution, ids: tuple[str, ...], rng: random.Random) -> tuple[Instance, Solution, dict[str, str]]:
    shuffled = list(ids); rng.shuffle(shuffled)
    mapping = dict(zip(ids, shuffled))
    nodes = {mapping.get(key, key): replace(node, id=mapping.get(key, key)) for key, node in instance.nodes.items()}
    new_instance = replace(instance, nodes=nodes, customer_ids=tuple(mapping.get(x, x) for x in instance.customer_ids),
                           station_ids=tuple(mapping.get(x, x) for x in instance.station_ids))
    routes = tuple(replace(r, node_ids=tuple(mapping.get(x, x) for x in r.node_ids), schedule=()) for r in solution.routes)
    return new_instance, replace(solution, routes=routes), mapping


def relabel_customers(instance: Instance, solution: Solution, rng: random.Random) -> tuple[Instance, Solution, dict[str, str]]:
    return _relabel(instance, solution, instance.customer_ids, rng)


def relabel_stations(instance: Instance, solution: Solution, rng: random.Random) -> tuple[Instance, Solution, dict[str, str]]:
    return _relabel(instance, solution, instance.station_ids, rng)


def permute_route_order(solution: Solution, rng: random.Random) -> Solution:
    routes = list(solution.routes); rng.shuffle(routes)
    return replace(solution, routes=tuple(routes))


def permute_move_list(moves: Sequence[Move], rng: random.Random) -> list[Move]:
    result = list(moves); rng.shuffle(result); return result


def ranking_correlation(left: Sequence[float], right: Sequence[float]) -> float:
    """Spearman rank correlation (ties receive average ranks), no scipy dependency."""
    if len(left) != len(right) or not left: return 0.0
    def ranks(values: Sequence[float]) -> list[float]:
        ordered = sorted(enumerate(values), key=lambda x: x[1]); out = [0.0] * len(values); i = 0
        while i < len(ordered):
            j = i
            while j + 1 < len(ordered) and ordered[j + 1][1] == ordered[i][1]: j += 1
            rank = (i + j + 2) / 2
            for k in range(i, j + 1): out[ordered[k][0]] = rank
            i = j + 1
        return out
    a, b = ranks(left), ranks(right); ma, mb = sum(a)/len(a), sum(b)/len(b)
    denom = sum((x-ma)**2 for x in a) * sum((y-mb)**2 for y in b)
    if denom <= 1e-18:
        # Both constant (all ties) ⇒ perfect rank agreement; mixed zero-variance ⇒ undefined/fail.
        left_var = sum((x - ma) ** 2 for x in a) <= 1e-18
        right_var = sum((y - mb) ** 2 for y in b) <= 1e-18
        return 1.0 if left_var and right_var else 0.0
    return float(sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True)) / denom**0.5)


def _move_signature(move: Move, mapping: dict[str, str] | None = None) -> tuple:
    """Stable move identity; optional ID mapping for post-relabel lookup."""
    map_id = (lambda x: mapping.get(x, x)) if mapping else (lambda x: x)
    return (
        move.move_type,
        move.route_i,
        move.route_j,
        move.indices,
        tuple(map_id(x) for x in move.segment),
        tuple(map_id(x) for x in move.station_ids),
    )


def _scheduled(instance: Instance, solution: Solution) -> Solution:
    routes = tuple(
        propagate_route(instance, route.node_ids, vehicle_index=route.vehicle_index)
        for route in solution.routes
    )
    return replace(solution, routes=routes)


def _feasible_moves(instance: Instance, solution: Solution, moves: Sequence[Move]) -> list[Move]:
    """compute_features requires a feasible move; filter before ranking/comparison."""
    return [m for m in moves if apply_move(instance, solution, m) is not None]


def _paired_invariance(moves: Sequence[Move], base_by_sig: dict[tuple, float], other_by_sig: dict[tuple, float],
                        remap: Callable[[Move], tuple]) -> dict[str, Any]:
    """Compare policy scores across a structural transform via a move-signature remap."""
    paired_left: list[float] = []
    paired_right: list[float] = []
    for move in moves:
        key = remap(move)
        if key not in other_by_sig:
            continue
        paired_left.append(base_by_sig[_move_signature(move)])
        paired_right.append(float(other_by_sig[key]))
    corr = ranking_correlation(paired_left, paired_right) if paired_left else 0.0
    max_abs = max((abs(a - b) for a, b in zip(paired_left, paired_right, strict=True)), default=float("inf"))
    return {
        "applicable": bool(paired_left),
        "ranking_correlation": corr,
        "passes": max_abs < 1e-9 and corr >= 0.999,
        "paired_moves": float(len(paired_left)),
        "max_abs_score_diff": float(max_abs if paired_left else -1.0),
    }


def _relabel_check(relabel_fn: Callable[[Instance, Solution, random.Random], tuple[Instance, Solution, dict[str, str]]],
                    policy: Policy, instance: Instance, solution: Solution, rng: random.Random,
                    normalizer: FeatureNormalizer | None = None) -> dict[str, float | bool]:
    solution = _scheduled(instance, solution)
    moves = _feasible_moves(instance, solution, enumerate_moves(instance, solution))
    base_by_sig = {_move_signature(m): _score(policy, compute_features(instance, solution, m), normalizer) for m in moves}
    relabeled, rel_solution, mapping = relabel_fn(instance, solution, rng)
    rel_solution = _scheduled(relabeled, rel_solution)
    rel_moves = _feasible_moves(relabeled, rel_solution, enumerate_moves(relabeled, rel_solution))
    rel_by_sig = {_move_signature(m): _score(policy, compute_features(relabeled, rel_solution, m), normalizer) for m in rel_moves}
    result = _paired_invariance(moves, base_by_sig, rel_by_sig, lambda m: _move_signature(m, mapping))
    result["mapping_size"] = float(len(mapping))
    return result


def execute_relabel_check(policy: Policy, instance: Instance, solution: Solution, rng: random.Random,
                           normalizer: FeatureNormalizer | None = None) -> dict[str, float | bool]:
    """Backward-compatible customer-relabel invariance check; see execute_challenge(CUSTOMER_RELABEL, ...)."""
    return _relabel_check(relabel_customers, policy, instance, solution, rng, normalizer)


# --- degeneracy detectors ----------------------------------------------------

def detect_constant_policy(policy: Policy, feature_vectors: Sequence[dict[str, float]]) -> bool:
    return len({round(evaluate(policy, f), 12) for f in feature_vectors}) <= 1


def detect_first_move_bias(policy: Policy, moves: Sequence[Move], feature_vectors: Sequence[dict[str, float]]) -> bool:
    if not moves: return False
    scores = [evaluate(policy, f) for f in feature_vectors]
    return scores[0] == max(scores) and all(s == scores[0] for s in scores)


def detect_move_type_collapse(policy: Policy, moves: Sequence[Move], feature_vectors: Sequence[dict[str, float]]) -> bool:
    if not moves: return False
    best = max(range(len(moves)), key=lambda i: evaluate(policy, feature_vectors[i]))
    return all(m.move_type == moves[best].move_type for m in moves)


def detect_ignores_charging_features(policy: Policy, feature_vectors: Sequence[dict[str, float]]) -> bool:
    names = ("delta_charging_distance", "delta_charging_time", "station_detour_contribution", "station_time_contribution")
    return all(evaluate(policy, f) == evaluate(policy, {**f, **{n: f.get(n, 0.) + 1. for n in names}}) for f in feature_vectors)


def detect_handcrafted_equivalence(policy: Policy, feature_vectors: Sequence[dict[str, float]], handcrafted: dict[str, Policy]) -> str | None:
    target = [evaluate(policy, f) for f in feature_vectors]
    for name, candidate in handcrafted.items():
        if all(abs(a - b) < 1e-9 for a, b in zip(target, [evaluate(candidate, f) for f in feature_vectors])):
            return name
    return None


# --- challenge catalogue: each handler returns {applicable, passed, details} ---

def _wrap(raw: dict[str, Any]) -> dict[str, Any]:
    return {"applicable": bool(raw.get("applicable", False)), "passed": bool(raw.get("passes", False)), "details": raw}


def _customer_relabel(policy: Policy, instance: Instance, solution: Solution, rng: random.Random,
                       normalizer: FeatureNormalizer | None = None, **_: Any) -> dict[str, Any]:
    return _wrap(_relabel_check(relabel_customers, policy, instance, solution, rng, normalizer))


def _station_relabel(policy: Policy, instance: Instance, solution: Solution, rng: random.Random,
                      normalizer: FeatureNormalizer | None = None, **_: Any) -> dict[str, Any]:
    return _wrap(_relabel_check(relabel_stations, policy, instance, solution, rng, normalizer))


def _route_order(policy: Policy, instance: Instance, solution: Solution, rng: random.Random,
                  normalizer: FeatureNormalizer | None = None, **_: Any) -> dict[str, Any]:
    solution = _scheduled(instance, solution)
    moves = _feasible_moves(instance, solution, enumerate_moves(instance, solution))
    base_by_sig = {_move_signature(m): _score(policy, compute_features(instance, solution, m), normalizer) for m in moves}
    permuted = permute_route_order(solution, rng)
    index_map = {old_i: new_i for new_i, route in enumerate(permuted.routes)
                 for old_i, original in enumerate(solution.routes) if original is route}
    perm_moves = _feasible_moves(instance, permuted, enumerate_moves(instance, permuted))
    perm_by_sig = {_move_signature(m): _score(policy, compute_features(instance, permuted, m), normalizer) for m in perm_moves}

    def remap(move: Move) -> tuple:
        route_j = index_map.get(move.route_j, move.route_j) if move.route_j is not None else None
        return (move.move_type, index_map.get(move.route_i, move.route_i), route_j, move.indices, move.segment, move.station_ids)

    return _wrap(_paired_invariance(moves, base_by_sig, perm_by_sig, remap))


def _move_order(policy: Policy, instance: Instance, solution: Solution, rng: random.Random,
                 normalizer: FeatureNormalizer | None = None, **_: Any) -> dict[str, Any]:
    solution = _scheduled(instance, solution)
    moves = _feasible_moves(instance, solution, enumerate_moves(instance, solution))
    if not moves:
        return {"applicable": False, "passed": False, "details": {"reason": "no feasible candidate moves"}}

    def features_of(candidate_moves: Sequence[Move]) -> list[dict[str, float]]:
        raw = [compute_features(instance, solution, m) for m in candidate_moves]
        return [normalizer.transform(f) if normalizer is not None else f for f in raw]

    original_best = select_move_by_policy(moves, features_of(moves), policy)
    permuted_moves = permute_move_list(moves, rng)
    permuted_best = select_move_by_policy(permuted_moves, features_of(permuted_moves), policy)
    same = (_move_signature(original_best) == _move_signature(permuted_best)) if original_best and permuted_best else (original_best is permuted_best)
    return {
        "applicable": True,
        "passed": bool(same),
        "details": {"num_moves": float(len(moves)), "order_changed": moves != permuted_moves},
    }


def _charging_feature_perturbation(policy: Policy, instance: Instance, solution: Solution, rng: random.Random,
                                    expect_sensitive: bool | None = None,
                                    normalizer: FeatureNormalizer | None = None, **_: Any) -> dict[str, Any]:
    solution = _scheduled(instance, solution)
    moves = _feasible_moves(instance, solution, enumerate_moves(instance, solution))
    if not moves:
        return {"applicable": False, "passed": False, "details": {"reason": "no feasible candidate moves"}}
    raw_vectors = [compute_features(instance, solution, m) for m in moves]
    vectors = [normalizer.transform(f) if normalizer is not None else f for f in raw_vectors]
    ignores = detect_ignores_charging_features(policy, vectors)
    passed = True if expect_sensitive is None else (expect_sensitive != ignores)
    return {"applicable": True, "passed": passed,
            "details": {"ignores_charging_features": ignores, "num_vectors": float(len(vectors))}}


def _handcrafted_equivalence(policy: Policy, instance: Instance, solution: Solution, rng: random.Random,
                              normalizer: FeatureNormalizer | None = None, **_: Any) -> dict[str, Any]:
    solution = _scheduled(instance, solution)
    moves = _feasible_moves(instance, solution, enumerate_moves(instance, solution))
    if not moves:
        return {"applicable": False, "passed": False, "details": {"reason": "no feasible candidate moves"}}
    raw_vectors = [compute_features(instance, solution, m) for m in moves]
    vectors = [normalizer.transform(f) if normalizer is not None else f for f in raw_vectors]
    match = detect_handcrafted_equivalence(policy, vectors, HANDCRAFTED_POLICIES)
    return {"applicable": True, "passed": match is None, "details": {"matches_handcrafted": match}}


def _strip_customers(solution: Solution, customer_ids: Sequence[str]) -> Solution:
    removed = set(customer_ids)
    routes = tuple(
        Route(r.vehicle_index, tuple(n for n in r.node_ids if n not in removed)) for r in solution.routes
    )
    return replace(solution, routes=routes)


def _fleet_increase(policy: Policy, instance: Instance, solution: Solution, rng: random.Random,
                     normalizer: FeatureNormalizer | None = None, **_: Any) -> dict[str, Any]:
    """Fail if the policy ranks a fleet-worsening removal-unit repair above an available
    fleet-preserving repair with an equal-or-better distance outcome.

    Unlike the fixed coupled-move catalogue (which can only shrink or preserve the fleet), the
    equal-budget removal-unit repair (:func:`chargecegis.construction.insert_customers_best_fit`)
    genuinely can grow the fleet when no existing route can absorb the removed customers, so this
    challenge is constructed from real repaired states rather than a synthetic scenario.
    """
    solution = _scheduled(instance, solution)
    before_vehicles = len(solution.routes)
    units = enumerate_removal_units(instance, solution, max_segment_length=3)
    pool = sample_candidate_pool(units, rng=rng, max_per_route=5, max_total=40)
    scored: list[tuple[RemovalUnit, float, int, float]] = []
    for unit in pool:
        destroyed = remove_empty_routes(_strip_customers(solution, unit.customer_ids), instance)
        repaired = insert_customers_best_fit(
            instance, destroyed, unit.customer_ids, rng=random.Random(rng.random())
        )
        repaired = remove_empty_routes(repaired, instance)
        try:
            feats = compute_features_for_solutions(instance, solution, repaired, unit)
        except ValueError:
            continue
        scored.append((unit, _score(policy, feats, normalizer), len(repaired.routes), feats["delta_distance_estimate"]))
    worsening = [t for t in scored if t[2] > before_vehicles]
    preserving = [t for t in scored if t[2] <= before_vehicles]
    if not worsening or not preserving:
        return {"applicable": False, "passed": False,
                "details": {"reason": "no comparable fleet-worsening/fleet-preserving removal-unit pair",
                            "before_vehicles": float(before_vehicles), "num_candidates": float(len(scored))}}
    best_worsening = max(worsening, key=lambda t: t[1])
    best_preserving = max(preserving, key=lambda t: t[1])
    violation = best_worsening[1] > best_preserving[1] and best_worsening[3] >= best_preserving[3]
    return {"applicable": True, "passed": not violation,
            "details": {"best_worsening_score": best_worsening[1], "best_preserving_score": best_preserving[1],
                        "num_worsening": float(len(worsening)), "num_preserving": float(len(preserving))}}


def _downstream_lateness(policy: Policy, instance: Instance, solution: Solution, rng: random.Random,
                          margin: float = 1.0, normalizer: FeatureNormalizer | None = None, **_: Any) -> dict[str, Any]:
    """Fail if the policy prefers a move that tightens downstream time slack with no distance benefit."""
    solution = _scheduled(instance, solution)
    moves = enumerate_moves(instance, solution)
    feasible = [(m, compute_features(instance, solution, m)) for m in moves if apply_move(instance, solution, m) is not None]
    if len(feasible) < 2:
        return {"applicable": False, "passed": False, "details": {"reason": "fewer than two feasible moves"}}
    scored = [(m, f, _score(policy, f, normalizer)) for m, f in feasible]
    violation: tuple[tuple, tuple] | None = None
    for move_a, features_a, score_a in scored:
        for move_b, features_b, score_b in scored:
            if move_a is move_b:
                continue
            same_distance = abs(features_a["delta_distance_estimate"] - features_b["delta_distance_estimate"]) < 1e-6
            riskier = features_a["minimum_time_slack_after"] < features_b["minimum_time_slack_after"] - margin
            if same_distance and riskier and score_a > score_b:
                violation = (_move_signature(move_a), _move_signature(move_b))
                break
        if violation:
            break
    return {"applicable": True, "passed": violation is None,
            "details": {"violation_pair": violation, "num_feasible": float(len(feasible))}}


def _no_feasible_station(policy: Policy, instance: Instance, solution: Solution, rng: random.Random,
                          normalizer: FeatureNormalizer | None = None, **_: Any) -> dict[str, Any]:
    """Fail if the policy prefers a no-alternative station move over an equal-or-better station-flexible one."""
    solution = _scheduled(instance, solution)
    moves = _feasible_moves(instance, solution, enumerate_moves(instance, solution))
    scored = [(m, f, _score(policy, f, normalizer)) for m in moves for f in [compute_features(instance, solution, m)]]
    zero_alt = [t for t in scored if t[1]["alternative_station_count"] == 0.0
                and t[0].move_type in (MoveType.STATION_REPLACEMENT, MoveType.STATION_REMOVAL)]
    others = [t for t in scored if t[1]["alternative_station_count"] > 0.0]
    if not zero_alt or not others:
        return {"applicable": False, "passed": False, "details": {"reason": "no comparable station-alternative moves"}}
    best_zero = max(zero_alt, key=lambda t: t[2])
    best_other = max(others, key=lambda t: t[2])
    violation = best_zero[2] > best_other[2] and best_zero[1]["delta_distance_estimate"] >= best_other[1]["delta_distance_estimate"]
    return {"applicable": True, "passed": not violation,
            "details": {"best_zero_alt_score": best_zero[2], "best_alternative_score": best_other[2]}}


def _tight_depot_horizon(policy: Policy, instance: Instance, solution: Solution, rng: random.Random,
                          tight_margin: float = 1.0, normalizer: FeatureNormalizer | None = None,
                          **_: Any) -> dict[str, Any]:
    """Tighten the depot due-time and require the policy's top move to keep the best available time slack."""
    scheduled = _scheduled(instance, solution)
    depot_returns = [stop.service_start for route in scheduled.routes for stop in route.schedule
                      if stop.node_id == instance.depot_id]
    if not depot_returns or not math.isfinite(max(depot_returns)):
        return {"applicable": False, "passed": False, "details": {"reason": "no finite depot return time available"}}
    tight_due = max(depot_returns) - tight_margin
    tight_depot = replace(instance.depot, due_time=tight_due)
    tight_instance = replace(instance, nodes={**instance.nodes, instance.depot_id: tight_depot})
    tight_solution = _scheduled(tight_instance, solution)
    moves = _feasible_moves(tight_instance, tight_solution, enumerate_moves(tight_instance, tight_solution))
    if not moves:
        return {"applicable": False, "passed": False, "details": {"reason": "no feasible candidate moves under tightened depot horizon"}}
    raw_features_list = [compute_features(tight_instance, tight_solution, m) for m in moves]
    features_list = [normalizer.transform(f) if normalizer is not None else f for f in raw_features_list]
    best = select_move_by_policy(moves, features_list, policy)
    assert best is not None  # moves is non-empty, so select_move_by_policy always returns a Move
    best_features = features_list[moves.index(best)]
    max_slack = max(f["minimum_time_slack_after"] for f in features_list)
    passed = best_features["minimum_time_slack_after"] >= max_slack - 1e-6
    return {"applicable": True, "passed": bool(passed),
            "details": {"tight_due_time": tight_due, "best_time_slack_after": best_features["minimum_time_slack_after"],
                        "max_time_slack_after": max_slack}}


_HANDLERS: dict[ChallengeType, Callable[..., dict[str, Any]]] = {
    ChallengeType.CUSTOMER_RELABEL: _customer_relabel,
    ChallengeType.STATION_RELABEL: _station_relabel,
    ChallengeType.ROUTE_ORDER: _route_order,
    ChallengeType.MOVE_ORDER: _move_order,
    ChallengeType.NO_FEASIBLE_STATION: _no_feasible_station,
    ChallengeType.TIGHT_DEPOT_HORIZON: _tight_depot_horizon,
    ChallengeType.FLEET_INCREASE: _fleet_increase,
    ChallengeType.DOWNSTREAM_LATENESS: _downstream_lateness,
    ChallengeType.CHARGING_FEATURE_PERTURBATION: _charging_feature_perturbation,
    ChallengeType.HANDCRAFTED_EQUIVALENCE: _handcrafted_equivalence,
}


def execute_challenge(challenge_type: str, policy: Policy, instance: Instance, solution: Solution,
                       rng: random.Random, normalizer: FeatureNormalizer | None = None,
                       **kwargs: Any) -> dict[str, Any]:
    """Run one catalogue challenge deterministically given rng; returns {applicable, passed, details}.

    ``normalizer``, when given, is applied to every feature vector before policy evaluation --
    the same normalize-then-evaluate contract equal-budget ranking uses (see
    :mod:`chargecegis.alns`), so a policy is challenged exactly as the solver would score it.
    """
    try:
        kind = ChallengeType(challenge_type)
    except ValueError as exc:
        raise ValueError(f"unknown challenge type: {challenge_type!r}") from exc
    return _HANDLERS[kind](policy, instance, solution, rng, normalizer=normalizer, **kwargs)


def execute_plan(policy: Policy, plan_challenges: Sequence[Any], instance: Instance, solution: Solution,
                  rng: random.Random, normalizer: FeatureNormalizer | None = None) -> list[dict[str, Any]]:
    """Execute a synthesizer-agent challenge plan sequentially, each with an independently derived rng."""
    results: list[dict[str, Any]] = []
    for challenge in plan_challenges:
        challenge_type: str | None
        if isinstance(challenge, str):
            challenge_type = challenge
        elif isinstance(challenge, dict):
            challenge_type = challenge.get("type")
        else:
            challenge_type = getattr(challenge, "type", None)
        try:
            result = execute_challenge(
                str(challenge_type), policy, instance, solution, random.Random(rng.random()), normalizer=normalizer
            )
        except ValueError as exc:
            result = {"applicable": False, "passed": False, "details": {"reason": str(exc)}}
        results.append({"type": str(challenge_type), **result})
    return results
