"""Deterministic ALNS with two ranking interfaces:

* the classic single-``Move`` coupled selection path (``move_selection_mode``: random / noop /
  handcrafted / policy over ``destroy_mode`` random / noop) -- unchanged, kept for backward
  compatibility with existing experiments and tests;
* an equal-budget ``RemovalUnit``-pool path (``destroy_mode="equal_budget"``), which scores every
  pooled removal unit by evaluating it in isolation, then applies exactly one repair to the
  selected top-k non-overlapping units per iteration so random/handcrafted/policy rankings spend
  the same per-iteration compute budget and are directly comparable.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import time
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from statistics import mean
from typing import Any, Literal

from chargecegis.construction import (
    ChargingReconstructionConfig,
    construct_initial_solution,
    construct_merged_initial_solution,
    insert_customers_best_fit,
)
from chargecegis.feasibility import evaluate_feasibility, evaluate_objective
from chargecegis.features import FeatureNormalizer, compute_features, compute_features_for_solutions
from chargecegis.moves import (
    Move,
    RemovalUnit,
    apply_move,
    enumerate_moves,
    enumerate_removal_units,
    move_hash,
    sample_candidate_pool,
    unit_hash,
)
from chargecegis.policy_dsl import Policy, evaluate, parse_policy, policy_hash
from chargecegis.problem import Instance, ObjectiveVector, Route, Solution
from chargecegis.search import HANDCRAFTED_POLICIES

MoveSelectionMode = Literal["random", "noop", "handcrafted", "policy"]
RankingMode = Literal["random", "handcrafted", "policy", "classic"]

# Method name -> ALNSConfig overrides for the equal-budget interface. Not wired into
# ``experiment.py`` by this module; provided as the canonical mapping for callers to build
# ``ALNSConfig(**{"handcrafted_name": ..., **EQUAL_BUDGET_METHODS[name]})``-style configs.
EQUAL_BUDGET_METHODS: dict[str, dict[str, Any]] = {
    "RANDOM_RANKING": {"destroy_mode": "equal_budget", "ranking_mode": "random"},
    "HANDCRAFTED_CHARGING_RANKING": {"destroy_mode": "equal_budget", "ranking_mode": "handcrafted", "handcrafted_name": "charging"},
    "HANDCRAFTED_TIME_RANKING": {"destroy_mode": "equal_budget", "ranking_mode": "handcrafted", "handcrafted_name": "time"},
    "HANDCRAFTED_COMBINED_RANKING": {"destroy_mode": "equal_budget", "ranking_mode": "handcrafted", "handcrafted_name": "combined"},
    "REFERENCE_DSL_RANKING": {"destroy_mode": "equal_budget", "ranking_mode": "handcrafted", "handcrafted_name": "reference"},
    "CLASSIC_ALNS_REFERENCE": {"destroy_mode": "random", "move_selection_mode": "random"},
}


@dataclass(frozen=True)
class ALNSConfig:
    seed: int = 2027
    max_iterations: int = 100
    destroy_fraction: float = 0.25
    initial_temperature: float = 5.0
    cooling_rate: float = 0.995
    destroy_mode: str = "random"
    move_selection_mode: MoveSelectionMode = "random"
    policy_path: str | None = None
    handcrafted_name: str = "combined"
    max_moves_per_type: int = 20
    charging: ChargingReconstructionConfig = field(default_factory=ChargingReconstructionConfig)
    normalizer: FeatureNormalizer | None = None
    policy: Policy | None = None
    policy_id: str = "none"
    # --- equal-budget removal-unit interface, active when destroy_mode == "equal_budget" ---
    ranking_mode: RankingMode = "random"
    removal_units_per_iteration: int = 5
    max_segment_length: int = 3
    candidate_pool_max_per_route: int = 5
    candidate_pool_max_total: int = 100
    use_merged_initial: bool = True


@dataclass
class EvaluatedCandidate:
    candidate: RemovalUnit
    resulting_solution: Solution
    features_raw: dict[str, float]
    features_normalized: dict[str, float]
    policy_score: float
    feasible: bool
    objective_delta: tuple[float, ...]
    runtime_ms: float


@dataclass
class MoveInvocation:
    iteration: int
    policy_id: str
    move_type: str
    candidate_count: int
    selected_move_hash: str
    policy_score: float
    feasible: bool
    vehicles_before: int
    vehicles_after: int
    distance_before: float
    distance_after: float
    station_count_before: int
    station_count_after: int
    customer_sequence_changed: bool
    station_sequence_changed: bool
    accepted: bool
    new_best: bool
    runtime_ms: float
    candidate_pool_hash: str = ""
    selected_unit_hashes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class ALNSResult:
    solution: Solution
    objective: ObjectiveVector
    feasible: bool
    iterations: int
    invocations: list[MoveInvocation] = field(default_factory=list)
    policy_calls: int = 0
    effective_moves: int = 0
    accepted_moves: int = 0
    new_best_moves: int = 0
    initial_solution_hash: str = ""
    final_solution_hash: str = ""
    time_to_best: float = 0.0
    runtime_seconds: float = 0.0


def solution_hash(solution: Solution) -> str:
    payload = json.dumps([list(r.node_ids) for r in solution.routes], separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def candidate_pool_hash(units: Sequence[RemovalUnit]) -> str:
    """Order-sensitive content hash of a sampled removal-unit pool (for reproducibility checks)."""
    payload = json.dumps([unit_hash(u) for u in units], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _station_count(instance: Instance, solution: Solution) -> int:
    return sum(1 for r in solution.routes for n in r.node_ids if n in instance.station_ids)


def _customer_seq(instance: Instance, solution: Solution) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(n for n in r.node_ids if n in instance.customer_ids) for r in solution.routes)


def _station_seq(instance: Instance, solution: Solution) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(n for n in r.node_ids if n in instance.station_ids) for r in solution.routes)


def remove_empty_routes(solution: Solution, instance: Instance) -> Solution:
    routes = [
        replace(route, vehicle_index=i)
        for i, route in enumerate(solution.routes)
        if any(n in instance.customer_ids for n in route.node_ids)
    ]
    return replace(solution, routes=tuple(routes))


def _strip_customers(solution: Solution, customer_ids: Sequence[str]) -> Solution:
    removed = set(customer_ids)
    routes = tuple(
        Route(r.vehicle_index, tuple(n for n in r.node_ids if n not in removed)) for r in solution.routes
    )
    return Solution(routes, solution.metadata)


def lex_key(obj: ObjectiveVector) -> tuple[int, int, float]:
    return (obj.infeasibility_count + obj.unserved_customers, obj.vehicles_used, obj.total_distance)


def accept_candidate(
    current_obj: ObjectiveVector,
    candidate_obj: ObjectiveVector,
    *,
    temperature: float,
    rng: random.Random,
) -> bool:
    """feasibility > vehicles > distance; SA only on distance when first two match."""
    cur, cand = lex_key(current_obj), lex_key(candidate_obj)
    if cur[0] == 0 and cand[0] > 0:
        return False
    if cand[0] != cur[0]:
        return cand[0] < cur[0]
    if cand[1] != cur[1]:
        return cand[1] < cur[1]
    if cand[2] <= cur[2]:
        return True
    if temperature <= 0:
        return False
    return rng.random() < math.exp(-(cand[2] - cur[2]) / temperature)


def noop_destroy(solution: Solution) -> tuple[Solution, tuple[str, ...]]:
    return solution, ()


def _random_removal(
    solution: Solution, instance: Instance, rng: random.Random, fraction: float
) -> tuple[Solution, tuple[str, ...]]:
    customers = [n for route in solution.routes for n in route.node_ids if n in instance.customer_ids]
    if not customers:
        return solution, ()
    count = max(1, round(len(customers) * fraction))
    removed = set(rng.sample(customers, min(count, len(customers))))
    retained: list[Route] = []
    for route in solution.routes:
        nodes = tuple(n for n in route.node_ids if n not in removed)
        if any(n in instance.customer_ids for n in nodes):
            retained.append(Route(route.vehicle_index, nodes))
    return Solution(tuple(retained)), tuple(sorted(removed))


def _load_policy(config: ALNSConfig, mode: str) -> tuple[Policy | None, str]:
    if config.policy is not None:
        return config.policy, config.policy_id or policy_hash(config.policy)[:16]
    if mode == "handcrafted":
        pol = HANDCRAFTED_POLICIES[config.handcrafted_name]
        return pol, f"handcrafted:{config.handcrafted_name}"
    if mode == "policy":
        if not config.policy_path:
            raise ValueError("policy mode requires policy_path or config.policy")
        pol = parse_policy(json.loads(Path(config.policy_path).read_text(encoding="utf-8")))
        return pol, f"file:{policy_hash(pol)[:16]}"
    return None, config.policy_id or str(mode)


def _select_coupled_move(
    instance: Instance,
    solution: Solution,
    config: ALNSConfig,
    policy: Policy | None,
    select_rng: random.Random,
    history: dict[str, float],
) -> tuple[Move | None, float, int]:
    raw = enumerate_moves(instance, solution, max_per_type=config.max_moves_per_type)
    scored: list[tuple[float, Move]] = []
    for move in raw:
        after = apply_move(instance, solution, move, config=config.charging)
        if after is None:
            continue
        feats = compute_features(instance, solution, move, history=history)
        if config.normalizer is not None:
            feats = config.normalizer.transform(feats)
        score = evaluate(policy, feats) if policy is not None else 0.0
        scored.append((score, move))
    if not scored:
        return None, 0.0, 0
    if policy is None or config.move_selection_mode == "random":
        return select_rng.choice([m for _, m in scored]), 0.0, len(scored)
    best_score, best_move = max(scored, key=lambda t: t[0])
    return best_move, float(best_score), len(scored)


def _evaluate_unit(
    instance: Instance,
    current: Solution,
    current_obj: ObjectiveVector,
    unit: RemovalUnit,
    *,
    config: ALNSConfig,
    ranking_mode: str,
    policy: Policy | None,
    repair_rng: random.Random,
    score_rng: random.Random,
    history: dict[str, float],
) -> EvaluatedCandidate:
    """Evaluate ``unit`` in isolation: remove just its customers, repair once, score once."""
    t0 = time.perf_counter()
    destroyed = remove_empty_routes(_strip_customers(current, unit.customer_ids), instance)
    trial_rng = random.Random(repair_rng.random())
    repaired = insert_customers_best_fit(
        instance, destroyed, unit.customer_ids, config=config.charging, rng=trial_rng
    )
    repaired = remove_empty_routes(repaired, instance)
    features_raw = compute_features_for_solutions(instance, current, repaired, unit, history=history)
    features_normalized = (
        config.normalizer.transform(features_raw) if config.normalizer is not None else features_raw
    )
    if ranking_mode == "random":
        score = score_rng.random()
    elif policy is not None:
        score = evaluate(policy, features_normalized)
    else:
        score = 0.0
    candidate_obj = evaluate_objective(instance, repaired)
    delta = tuple(c - b for c, b in zip(lex_key(candidate_obj), lex_key(current_obj)))
    return EvaluatedCandidate(
        candidate=unit,
        resulting_solution=repaired,
        features_raw=features_raw,
        features_normalized=features_normalized,
        policy_score=float(score),
        feasible=candidate_obj.infeasibility_count == 0,
        objective_delta=delta,
        runtime_ms=(time.perf_counter() - t0) * 1000.0,
    )


def _select_top_k_non_overlapping(
    evaluated: list[EvaluatedCandidate], k: int
) -> list[EvaluatedCandidate]:
    """Highest-score-first greedy pick whose *customers* sum to at most ``k``.

    ``k`` is a shared customer-removal budget, not a soft unit count. Ranking order may change
    *which* units are chosen, but every method that sees the same pool and the same ``k`` removes
    the same number of customers whenever the pool contains enough non-overlapping coverage
    (singleton units guarantee this once ``n_customers >= k``). Longer segments are accepted only
    when they fit entirely inside the remaining budget, so one method cannot spend the iteration
    on a 25-customer destroy while another spends it on a 1-customer move.
    """
    ordered = sorted(
        evaluated,
        key=lambda c: (-c.policy_score, len(c.candidate.customer_ids), unit_hash(c.candidate)),
    )
    selected: list[EvaluatedCandidate] = []
    used: set[str] = set()
    customers_selected = 0
    for cand in ordered:
        customers = set(cand.candidate.customer_ids)
        if not customers or customers & used:
            continue
        if customers_selected + len(customers) > k:
            continue
        selected.append(cand)
        used |= customers
        customers_selected += len(customers)
        if customers_selected >= k:
            break
    return selected


def _run_equal_budget_iteration(
    instance: Instance,
    current: Solution,
    current_obj: ObjectiveVector,
    config: ALNSConfig,
    ranking_mode: str,
    policy: Policy | None,
    *,
    pool_rng: random.Random,
    score_rng: random.Random,
    repair_rng: random.Random,
    history: dict[str, float],
) -> tuple[Solution, list[EvaluatedCandidate], str, tuple[str, ...]]:
    """One equal-budget iteration: pool -> score every unit once -> select top-k -> repair once.

    Pool generation (steps enumerate + sample) depends only on ``current`` and ``pool_rng``, never
    on ``ranking_mode``, so random/handcrafted/policy runs sharing a seed and solution state see
    an identical ``candidate_pool_hash`` at the start of each iteration.
    """
    units = enumerate_removal_units(instance, current, max_segment_length=config.max_segment_length)
    pool = sample_candidate_pool(
        units, rng=pool_rng,
        max_per_route=config.candidate_pool_max_per_route,
        max_total=config.candidate_pool_max_total,
    )
    pool_hash = candidate_pool_hash(pool)
    if not pool:
        return current, [], pool_hash, ()

    evaluated = [
        _evaluate_unit(
            instance, current, current_obj, unit, config=config, ranking_mode=ranking_mode,
            policy=policy, repair_rng=repair_rng, score_rng=score_rng, history=history,
        )
        for unit in pool
    ]
    selected = _select_top_k_non_overlapping(evaluated, config.removal_units_per_iteration)
    selected_customers = tuple(sorted({c for cand in selected for c in cand.candidate.customer_ids}))
    if not selected_customers:
        return current, evaluated, pool_hash, ()

    destroyed = remove_empty_routes(_strip_customers(current, selected_customers), instance)
    repaired = insert_customers_best_fit(
        instance, destroyed, selected_customers, config=config.charging, rng=repair_rng
    )
    repaired = remove_empty_routes(repaired, instance)
    selected_hashes = tuple(unit_hash(cand.candidate) for cand in selected)
    return repaired, evaluated, pool_hash, selected_hashes


def run_alns(
    instance: Instance,
    *,
    config: ALNSConfig = ALNSConfig(),
    initial: Solution | None = None,
) -> ALNSResult:
    select_rng = random.Random(config.seed)
    destroy_rng = random.Random(config.seed + 1_000_003)
    repair_rng = random.Random(config.seed + 2_000_003)
    accept_rng = random.Random(config.seed + 3_000_003)
    pool_rng = random.Random(config.seed + 4_000_003)
    score_rng = random.Random(config.seed + 5_000_003)

    equal_budget = config.destroy_mode == "equal_budget"
    policy_mode = config.ranking_mode if equal_budget else config.move_selection_mode
    policy, policy_id = _load_policy(config, policy_mode)
    noop_control = (not equal_budget) and config.destroy_mode == "noop" and config.move_selection_mode == "noop"
    coupled = (not equal_budget) and (not noop_control) and config.move_selection_mode in {"policy", "handcrafted"}
    classic = (not equal_budget) and (not noop_control) and (not coupled)
    record_invocations = coupled or equal_budget

    if initial is not None:
        started = initial
    elif config.use_merged_initial:
        started = construct_merged_initial_solution(instance, seed=config.seed, config=config.charging).solution
    else:
        started = construct_initial_solution(instance).solution
    current = remove_empty_routes(started, instance)
    current_obj = evaluate_objective(instance, current)
    best, best_obj = current, current_obj
    temperature = config.initial_temperature
    invocations: list[MoveInvocation] = []
    history = {"acceptance_rate": 0.0, "improvement_rate": 0.0}
    accepted_n = improved_n = calls = 0
    t0 = time.perf_counter()
    time_to_best = 0.0
    init_hash = solution_hash(current)

    for iteration in range(config.max_iterations):
        select_rng.random()
        t_iter = time.perf_counter()
        before, before_obj = current, current_obj
        move: Move | None = None
        score, n_cand = 0.0, 0
        pool_hash = ""
        selected_hashes: tuple[str, ...] = ()

        if noop_control:
            candidate, candidate_obj = current, current_obj
            accepted = False
        elif equal_budget:
            calls += 1
            candidate, evaluated, pool_hash, selected_hashes = _run_equal_budget_iteration(
                instance, current, current_obj, config, config.ranking_mode, policy,
                pool_rng=pool_rng, score_rng=score_rng, repair_rng=repair_rng, history=history,
            )
            n_cand = len(evaluated)
            selected_scores = [c.policy_score for c in evaluated if unit_hash(c.candidate) in selected_hashes]
            score = mean(selected_scores) if selected_scores else 0.0
            candidate_obj = evaluate_objective(instance, candidate)
            accepted = accept_candidate(current_obj, candidate_obj, temperature=temperature, rng=accept_rng)
        elif coupled:
            move, score, n_cand = _select_coupled_move(
                instance, current, config, policy, select_rng, history
            )
            calls += 1
            if move is None:
                candidate, candidate_obj, accepted = current, current_obj, False
            else:
                after = apply_move(instance, current, move, config=config.charging)
                assert after is not None
                candidate = remove_empty_routes(after, instance)
                candidate_obj = evaluate_objective(instance, candidate)
                accepted = accept_candidate(
                    current_obj, candidate_obj, temperature=temperature, rng=accept_rng
                )
        else:
            assert classic
            if config.destroy_mode == "noop":
                destroyed, removed = noop_destroy(current)
            else:
                destroyed, removed = _random_removal(
                    current, instance, destroy_rng, config.destroy_fraction
                )
            if removed:
                candidate = insert_customers_best_fit(
                    instance, destroyed, removed, config=config.charging, rng=repair_rng
                )
            else:
                candidate = destroyed
            candidate = remove_empty_routes(candidate, instance)
            candidate_obj = evaluate_objective(instance, candidate)
            accepted = accept_candidate(
                current_obj, candidate_obj, temperature=temperature, rng=accept_rng
            )

        new_best = False
        if accepted:
            accepted_n += 1
            current, current_obj = candidate, candidate_obj
            if lex_key(current_obj) < lex_key(best_obj):
                best, best_obj = current, current_obj
                new_best = True
                improved_n += 1
                time_to_best = time.perf_counter() - t0

        if record_invocations:
            invocations.append(
                MoveInvocation(
                    iteration=iteration,
                    policy_id=policy_id,
                    move_type=move.move_type.value if move else ("EQUAL_BUDGET" if equal_budget else "none"),
                    candidate_count=n_cand,
                    selected_move_hash=move_hash(move) if move else "",
                    policy_score=score,
                    feasible=candidate_obj.infeasibility_count == 0,
                    vehicles_before=before_obj.vehicles_used,
                    vehicles_after=candidate_obj.vehicles_used,
                    distance_before=before_obj.total_distance,
                    distance_after=candidate_obj.total_distance,
                    station_count_before=_station_count(instance, before),
                    station_count_after=_station_count(instance, candidate),
                    customer_sequence_changed=_customer_seq(instance, before)
                    != _customer_seq(instance, candidate),
                    station_sequence_changed=_station_seq(instance, before)
                    != _station_seq(instance, candidate),
                    accepted=accepted,
                    new_best=new_best,
                    runtime_ms=(time.perf_counter() - t_iter) * 1000,
                    candidate_pool_hash=pool_hash,
                    selected_unit_hashes=selected_hashes,
                )
            )
            history["acceptance_rate"] = accepted_n / max(calls, 1)
            history["improvement_rate"] = improved_n / max(calls, 1)

        temperature *= config.cooling_rate

    report = evaluate_feasibility(instance, best)
    return ALNSResult(
        solution=best,
        objective=best_obj,
        feasible=report.feasible,
        iterations=config.max_iterations,
        invocations=invocations,
        policy_calls=calls,
        effective_moves=sum(
            1 for i in invocations if i.customer_sequence_changed or i.station_sequence_changed
        ),
        accepted_moves=sum(1 for i in invocations if i.accepted),
        new_best_moves=sum(1 for i in invocations if i.new_best),
        initial_solution_hash=init_hash,
        final_solution_hash=solution_hash(best),
        time_to_best=time_to_best,
        runtime_seconds=time.perf_counter() - t0,
    )
