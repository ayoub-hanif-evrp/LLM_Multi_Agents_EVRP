"""Explicit route-elimination operator with trusted evaluator acceptance."""
from __future__ import annotations

import random
import time

from evrptw_autolab.backbone.alns import DEFAULT_REPAIR_SCORING_MODE
from evrptw_autolab.backbone.regret_repair import repair_regret2
from evrptw_autolab.backbone.util import (
    clone_solution,
    evaluate,
    is_better,
    served_request_nodes,
)
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2


def _request_nodes_on_route(spec: ProblemSpecV2, route) -> list[str]:
    ids = []
    for stop in route:
        if stop.event == "depot":
            continue
        node = spec.node_map.get(stop.node_id)
        if node is None:
            continue
        if node.kind in {"customer", "pickup", "delivery"}:
            ids.append(stop.node_id)
    return ids


def _select_route_index(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    rng: random.Random,
    strategy: str,
) -> int | None:
    if len(solution.routes) < 2:
        return None
    scored: list[tuple[float, int]] = []
    for idx, route in enumerate(solution.routes):
        customers = _request_nodes_on_route(spec, route)
        if not customers:
            continue
        if strategy == "fewest_customers":
            key = float(len(customers))
        elif strategy == "lowest_utilization":
            key = float(len(customers))
        elif strategy == "random":
            key = rng.random()
        else:
            key = float(len(customers))
        scored.append((key, idx))
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1]))
    return scored[0][1]


def eliminate_one_route(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    rng: random.Random,
    *,
    strategy: str = "fewest_customers",
    deadline: float | None = None,
    repair_scoring_mode: str = DEFAULT_REPAIR_SCORING_MODE,
    use_regret: bool = True,
) -> tuple[SolutionV2, dict]:
    """Try to remove one route and reinsert its customers into the remainder.

    Returns (best_solution, stats). Never returns a worse trusted incumbent.
    """
    stats = {
        "attempted": False,
        "success": False,
        "strategy": strategy,
        "selected_route": None,
        "customers_moved": 0,
        "reason": "",
    }
    if deadline is not None and time.monotonic() > deadline:
        stats["reason"] = "deadline"
        return solution, stats
    if spec.capabilities.pickup_delivery:
        stats["reason"] = "pd_not_supported_in_v1"
        return solution, stats

    idx = _select_route_index(spec, solution, rng, strategy)
    if idx is None:
        stats["reason"] = "no_eligible_route"
        return solution, stats

    customers = _request_nodes_on_route(spec, solution.routes[idx])
    if not customers:
        stats["reason"] = "empty_route"
        return solution, stats

    stats["attempted"] = True
    stats["selected_route"] = idx
    stats["customers_moved"] = len(customers)

    destroyed = clone_solution(solution)
    destroyed.routes = [r for i, r in enumerate(destroyed.routes) if i != idx]
    destroyed.vehicle_assignments = [
        a for i, a in enumerate(destroyed.vehicle_assignments) if i != idx
    ]
    # Drop stations that no longer belong to kept routes; energy repair rebuilds.
    cleaned_routes = []
    for route in destroyed.routes:
        cleaned_routes.append(
            [
                stop
                for stop in route
                if stop.event == "depot"
                or spec.node_map[stop.node_id].kind in {"customer", "pickup", "delivery"}
            ]
        )
    destroyed.routes = cleaned_routes

    removed: list[tuple[str, ...]] = [(cid,) for cid in customers]
    if use_regret:
        candidate = repair_regret2(
            spec,
            destroyed,
            removed,
            rng,
            optimize_partial_charges=True,
            deadline=deadline,
            repair_scoring_mode=repair_scoring_mode,
        )
    else:
        from evrptw_autolab.backbone.alns import repair_greedy

        candidate = repair_greedy(
            spec,
            destroyed,
            removed,
            rng,
            policy=None,
            optimize_partial_charges=True,
            deadline=deadline,
            repair_scoring_mode=repair_scoring_mode,
        )

    # Must not reopen an equivalent extra route and call it elimination.
    before = evaluate(spec, solution)
    after = evaluate(spec, candidate)
    if not after.feasible:
        stats["reason"] = "infeasible_reinsertion"
        return solution, stats
    if after.vehicles >= before.vehicles:
        stats["reason"] = "fleet_not_reduced"
        return solution, stats
    if not is_better(after, before):
        stats["reason"] = "objective_not_improved"
        return solution, stats
    stats["success"] = True
    stats["reason"] = "accepted"
    candidate.metadata["route_elimination"] = stats
    return candidate, stats


def eliminate_routes_improve(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    rng: random.Random,
    *,
    max_attempts: int = 8,
    strategy: str = "fewest_customers",
    deadline: float | None = None,
    repair_scoring_mode: str = DEFAULT_REPAIR_SCORING_MODE,
) -> SolutionV2:
    """Repeated trusted route-elimination attempts. Failed attempts do not damage incumbent."""
    current = clone_solution(solution)
    attempts = []
    for _ in range(max_attempts):
        if deadline is not None and time.monotonic() > deadline:
            break
        if len(current.routes) < 2:
            break
        current, stats = eliminate_one_route(
            spec,
            current,
            rng,
            strategy=strategy,
            deadline=deadline,
            repair_scoring_mode=repair_scoring_mode,
            use_regret=True,
        )
        attempts.append(stats)
        if not stats.get("success"):
            # Rotate strategy slightly on failure.
            if strategy == "fewest_customers":
                strategy = "random"
            else:
                strategy = "fewest_customers"
    current.metadata["route_elimination_attempts"] = attempts
    current.metadata["route_elimination_successes"] = sum(
        1 for item in attempts if item.get("success")
    )
    return current


def covered_customers(spec: ProblemSpecV2, solution: SolutionV2) -> set[str]:
    return {
        stop.node_id
        for route in solution.routes
        for stop in route
        if stop.node_id in served_request_nodes(spec)
    }
