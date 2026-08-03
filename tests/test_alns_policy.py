"""ALNS control paths and the equal-budget removal-unit ranking contract.

Equal-budget ranking methods (random / handcrafted / policy) must share the same merged initial
solution, the same candidate pool (and hash), and the same removal-unit budget ``k`` per
iteration -- only the ranking function may differ. ``CLASSIC_ALNS_REFERENCE`` uses an unrelated
(unequal-budget) interface and must never be mixed into that comparison.
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Literal

import pytest

from chargecegis.alns import (
    ALNSConfig,
    EvaluatedCandidate,
    _run_equal_budget_iteration,
    _select_top_k_non_overlapping,  # exercising the selection internals directly, by design
    accept_candidate,
    remove_empty_routes,
    run_alns,
    solution_hash,
)
from chargecegis.construction import construct_initial_solution, construct_merged_initial_solution
from chargecegis.data import load_instance
from chargecegis.moves import RemovalUnit
from chargecegis.problem import ObjectiveVector, Route, Solution

ROOT = Path(__file__).resolve().parents[1]
SCHNEIDER = ROOT / "dataset" / "schneider" / "raw_instances"


@pytest.fixture(scope="module")
def small_instance():
    return load_instance(SCHNEIDER / "c101C5.txt")


@pytest.fixture(scope="module")
def small_solution(small_instance):
    result = construct_initial_solution(small_instance)
    assert result.feasible
    return result.solution


def test_noop_control_is_deterministic_and_never_moves(small_instance, small_solution) -> None:
    config = ALNSConfig(seed=2027, max_iterations=5, destroy_mode="noop", move_selection_mode="noop")
    a = run_alns(small_instance, config=config, initial=small_solution)
    b = run_alns(small_instance, config=config, initial=small_solution)
    assert a.objective.as_tuple() == b.objective.as_tuple()
    assert solution_hash(a.solution) == solution_hash(b.solution) == solution_hash(small_solution)
    assert a.policy_calls == 0


def test_equal_budget_ranking_methods_share_initial_hash_pool_hash_and_k(small_instance) -> None:
    merged = construct_merged_initial_solution(small_instance, seed=0).solution
    results = {}
    combos: list[tuple[Literal["random", "handcrafted"], str]] = [
        ("random", "combined"), ("handcrafted", "combined"), ("handcrafted", "charging"),
    ]
    for ranking_mode, handcrafted_name in combos:
        config = ALNSConfig(
            seed=0, max_iterations=1, destroy_mode="equal_budget", ranking_mode=ranking_mode,
            handcrafted_name=handcrafted_name, removal_units_per_iteration=4,
        )
        results[(ranking_mode, handcrafted_name)] = run_alns(small_instance, config=config, initial=merged)
    initial_hashes = {r.initial_solution_hash for r in results.values()}
    pool_hashes = {r.invocations[0].candidate_pool_hash for r in results.values()}
    candidate_counts = {r.invocations[0].candidate_count for r in results.values()}
    assert len(initial_hashes) == 1
    assert len(pool_hashes) == 1
    assert len(candidate_counts) == 1

    # Shared customer-removal budget: every ranking method must remove exactly k customers when
    # the pool covers at least k distinct customers (true for c101C5 with k=4).
    from chargecegis.feasibility import evaluate_objective
    from chargecegis.moves import unit_hash
    from chargecegis.search import HANDCRAFTED_POLICIES

    customer_budgets: list[int] = []
    for ranking_mode, handcrafted_name in combos:
        config = ALNSConfig(
            seed=0, max_iterations=1, destroy_mode="equal_budget", ranking_mode=ranking_mode,
            handcrafted_name=handcrafted_name, removal_units_per_iteration=4,
        )
        policy = HANDCRAFTED_POLICIES[handcrafted_name] if ranking_mode == "handcrafted" else None
        _repaired, evaluated, _pool_hash, selected_hashes = _run_equal_budget_iteration(
            small_instance,
            merged,
            evaluate_objective(small_instance, merged),
            config,
            ranking_mode,
            policy,
            pool_rng=random.Random(0),
            score_rng=random.Random(1),
            repair_rng=random.Random(2),
            history={},
        )
        selected = [c for c in evaluated if unit_hash(c.candidate) in set(selected_hashes)]
        n_customers = sum(len(c.candidate.customer_ids) for c in selected)
        customer_budgets.append(n_customers)
        assert n_customers <= 4
    assert customer_budgets == [4, 4, 4]


def test_classic_alns_reference_does_not_record_equal_budget_invocations(small_instance, small_solution) -> None:
    config = ALNSConfig(seed=2027, max_iterations=5, destroy_mode="random", move_selection_mode="random")
    result = run_alns(small_instance, config=config, initial=small_solution)
    assert result.feasible
    assert result.invocations == []
    assert result.policy_calls == 0


def test_accept_candidate_rejects_higher_fleet_even_with_lower_distance() -> None:
    """Fleet size is the second lexicographic key: more vehicles must never be accepted just
    because distance improved, regardless of temperature."""
    rng = random.Random(0)
    current = ObjectiveVector(infeasibility_count=0, vehicles_used=2, total_distance=500.0)
    higher_fleet_candidate = ObjectiveVector(infeasibility_count=0, vehicles_used=3, total_distance=10.0)
    for temperature in (0.0, 1.0, 100.0):
        assert not accept_candidate(current, higher_fleet_candidate, temperature=temperature, rng=rng)


def test_remove_empty_routes_drops_customerless_routes_and_renumbers(small_instance) -> None:
    depot = small_instance.depot_id
    customer = small_instance.customer_ids[0]
    kept = Route(0, (depot, customer, depot))
    empty = Route(1, (depot, depot))
    solution = Solution((kept, empty))
    result = remove_empty_routes(solution, small_instance)
    assert len(result.routes) == 1
    assert result.routes[0].vehicle_index == 0
    assert result.routes[0].node_ids == kept.node_ids


def _fake_candidate(route_index: int, customer: str, score: float) -> EvaluatedCandidate:
    unit = RemovalUnit(
        route_index=route_index, start_customer_position=0, end_customer_position=0,
        customer_ids=(customer,),
    )
    return EvaluatedCandidate(
        candidate=unit, resulting_solution=Solution(()), features_raw={}, features_normalized={},
        policy_score=score, feasible=True, objective_delta=(0, 0, 0.0), runtime_ms=0.0,
    )


def test_equal_budget_top_k_selection_tracks_score_ranking_not_arrival_order() -> None:
    """The one place ranking_mode (random vs handcrafted vs policy) actually changes behavior on
    a fixed pool: whichever candidates score highest are selected, independent of pool order."""
    handcrafted_like_scores = [
        _fake_candidate(0, "c1", score=1.0),
        _fake_candidate(0, "c2", score=5.0),
        _fake_candidate(1, "c3", score=3.0),
    ]
    selected = _select_top_k_non_overlapping(handcrafted_like_scores, k=2)
    assert [c.candidate.customer_ids[0] for c in selected] == ["c2", "c3"]

    random_like_scores = [
        _fake_candidate(0, "c1", score=9.0),
        _fake_candidate(0, "c2", score=0.5),
        _fake_candidate(1, "c3", score=0.2),
    ]
    selected_random = _select_top_k_non_overlapping(random_like_scores, k=2)
    assert [c.candidate.customer_ids[0] for c in selected_random] == ["c1", "c2"]
