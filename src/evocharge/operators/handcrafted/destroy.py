"""Handcrafted destroy operators (immutable inputs)."""

from __future__ import annotations

import math
import random
from collections.abc import Callable

from evocharge.distances.euclidean import euclidean_distance
from evocharge.domain.instance import Instance
from evocharge.domain.route import Route
from evocharge.domain.solution import Solution
from evocharge.operators.api import DestroyResult, OperatorContext
from evocharge.solver.charging_repair import repair_charging
from evocharge.solver.route_utils import customer_sequence_of


def _copy_solution(solution: Solution) -> Solution:
    routes = tuple(
        Route(
            vehicle_index=r.vehicle_index,
            node_ids=r.node_ids,
            schedule=r.schedule,
            metadata=dict(r.metadata),
        )
        for r in solution.routes
    )
    return Solution(routes=routes, metadata=dict(solution.metadata))


def _remove_customers(
    instance: Instance,
    solution: Solution,
    to_remove: set[str],
    *,
    cache,
    bounds=None,
    profiler=None,
) -> Solution:
    new_routes: list[Route] = []
    for route in solution.routes:
        remaining = tuple(c for c in customer_sequence_of(route, instance) if c not in to_remove)
        if not remaining:
            continue
        repaired = repair_charging(
            instance,
            remaining,
            vehicle_index=len(new_routes),
            cache=cache,
            bounds=bounds,
            profiler=profiler,
        )
        if repaired.status == "success" and repaired.route is not None:
            new_routes.append(repaired.route)
        else:
            continue
    return Solution(
        routes=tuple(
            Route(vehicle_index=i, node_ids=r.node_ids, schedule=r.schedule, metadata=r.metadata)
            for i, r in enumerate(new_routes)
        ),
        metadata=dict(solution.metadata),
    )


def _n_remove(instance: Instance, fraction: float) -> int:
    n = len(instance.customer_ids)
    return max(1, min(n, int(math.ceil(n * fraction))))


def random_removal(
    solution: Solution,
    context: OperatorContext,
    rng: random.Random,
) -> DestroyResult:
    original = _copy_solution(solution)
    n = _n_remove(context.instance, context.destroy_fraction)
    pool = list(context.instance.customer_ids)
    rng.shuffle(pool)
    removed = tuple(pool[:n])
    new_sol = _remove_customers(
        context.instance,
        solution,
        set(removed),
        cache=context.cache,
        bounds=context.repair_bounds,
        profiler=context.profiler,
    )
    assert original.routes == solution.routes  # input not mutated
    return DestroyResult(solution=new_sol, removed_customers=removed, operator="random_removal")


def worst_cost_removal(
    solution: Solution,
    context: OperatorContext,
    rng: random.Random,
) -> DestroyResult:
    _ = rng
    instance = context.instance
    scores: list[tuple[float, str]] = []
    for route in solution.routes:
        customers = customer_sequence_of(route, instance)
        for c in customers:
            # Cost contribution proxy: distance to neighbors in route
            nodes = route.node_ids
            idxs = [i for i, nid in enumerate(nodes) if nid == c]
            if not idxs:
                continue
            i = idxs[0]
            prev_id, next_id = nodes[i - 1], nodes[i + 1]
            from evocharge.distances.matrix import DistanceMatrix

            matrix = DistanceMatrix(instance)
            detour = (
                matrix.get(prev_id, c).distance
                + matrix.get(c, next_id).distance
                - matrix.get(prev_id, next_id).distance
            )
            scores.append((detour, c))
    scores.sort(reverse=True)
    n = _n_remove(instance, context.destroy_fraction)
    removed = tuple(c for _, c in scores[:n])
    new_sol = _remove_customers(
        instance,
        solution,
        set(removed),
        cache=context.cache,
        bounds=context.repair_bounds,
        profiler=context.profiler,
    )
    return DestroyResult(solution=new_sol, removed_customers=removed, operator="worst_cost_removal")


def relatedness_removal(
    solution: Solution,
    context: OperatorContext,
    rng: random.Random,
) -> DestroyResult:
    instance = context.instance
    customers = list(instance.customer_ids)
    seed = rng.choice(customers)
    seed_node = instance.nodes[seed]

    def relatedness(cid: str) -> float:
        node = instance.nodes[cid]
        dist = 0.0
        if seed_node.coordinates and node.coordinates:
            dist = euclidean_distance(seed_node, node)
        tw = abs(seed_node.ready_time - node.ready_time)
        return dist + tw

    ranked = sorted(customers, key=relatedness)
    n = _n_remove(instance, context.destroy_fraction)
    removed = tuple(ranked[:n])
    new_sol = _remove_customers(
        instance,
        solution,
        set(removed),
        cache=context.cache,
        bounds=context.repair_bounds,
        profiler=context.profiler,
    )
    return DestroyResult(
        solution=new_sol,
        removed_customers=removed,
        operator="relatedness_removal",
        metadata={"seed_customer": seed},
    )


def route_removal(
    solution: Solution,
    context: OperatorContext,
    rng: random.Random,
) -> DestroyResult:
    if not solution.routes:
        return DestroyResult(solution=solution, removed_customers=(), operator="route_removal")
    route = rng.choice(list(solution.routes))
    removed = customer_sequence_of(route, context.instance)
    keep = [r for r in solution.routes if r.vehicle_index != route.vehicle_index]
    new_sol = Solution(
        routes=tuple(
            Route(vehicle_index=i, node_ids=r.node_ids, schedule=r.schedule, metadata=r.metadata)
            for i, r in enumerate(keep)
        ),
        metadata=dict(solution.metadata),
    )
    return DestroyResult(solution=new_sol, removed_customers=removed, operator="route_removal")


def time_window_critical_removal(
    solution: Solution,
    context: OperatorContext,
    rng: random.Random,
) -> DestroyResult:
    _ = rng
    instance = context.instance
    scores: list[tuple[float, str]] = []
    for route in solution.routes:
        for stop in route.schedule:
            if stop.node_id not in instance.customer_ids:
                continue
            # Smaller slack => more critical
            scores.append((-stop.time_slack, stop.node_id))
    scores.sort(reverse=True)
    n = _n_remove(instance, context.destroy_fraction)
    removed = tuple(dict.fromkeys(c for _, c in scores[: n * 2]))[:n]
    new_sol = _remove_customers(
        instance,
        solution,
        set(removed),
        cache=context.cache,
        bounds=context.repair_bounds,
        profiler=context.profiler,
    )
    return DestroyResult(
        solution=new_sol,
        removed_customers=removed,
        operator="time_window_critical_removal",
    )


def low_energy_slack_removal(
    solution: Solution,
    context: OperatorContext,
    rng: random.Random,
) -> DestroyResult:
    _ = rng
    instance = context.instance
    scores: list[tuple[float, str]] = []
    for route in solution.routes:
        for stop in route.schedule:
            if stop.node_id not in instance.customer_ids:
                continue
            scores.append((stop.energy_slack, stop.node_id))
    scores.sort()  # lowest slack first
    n = _n_remove(instance, context.destroy_fraction)
    removed = tuple(dict.fromkeys(c for _, c in scores[: n * 2]))[:n]
    new_sol = _remove_customers(
        instance,
        solution,
        set(removed),
        cache=context.cache,
        bounds=context.repair_bounds,
        profiler=context.profiler,
    )
    return DestroyResult(
        solution=new_sol,
        removed_customers=removed,
        operator="low_energy_slack_removal",
    )


def charging_dependency_removal(
    solution: Solution,
    context: OperatorContext,
    rng: random.Random,
) -> DestroyResult:
    """Remove customers on routes with many charging stops / high charging time."""
    _ = rng
    instance = context.instance
    route_scores: list[tuple[float, int, Route]] = []
    for idx, route in enumerate(solution.routes):
        n_stations = sum(1 for nid in route.node_ids if nid in set(instance.station_ids))
        charge_time = sum(s.charging_duration for s in route.schedule)
        route_scores.append((float(n_stations) + float(charge_time), idx, route))
    route_scores.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    if not route_scores:
        return DestroyResult(
            solution=solution, removed_customers=(), operator="charging_dependency_removal"
        )
    target = route_scores[0][2]
    removed = customer_sequence_of(target, instance)
    # Remove half if large
    n = max(1, len(removed) // 2) if len(removed) > 2 else len(removed)
    removed = removed[:n]
    new_sol = _remove_customers(
        instance,
        solution,
        set(removed),
        cache=context.cache,
        bounds=context.repair_bounds,
        profiler=context.profiler,
    )
    return DestroyResult(
        solution=new_sol,
        removed_customers=removed,
        operator="charging_dependency_removal",
    )


DESTROY_OPERATORS: dict[str, Callable[..., DestroyResult]] = {
    "random_removal": random_removal,
    "worst_cost_removal": worst_cost_removal,
    "relatedness_removal": relatedness_removal,
    "route_removal": route_removal,
    "time_window_critical_removal": time_window_critical_removal,
    "low_energy_slack_removal": low_energy_slack_removal,
    "charging_dependency_removal": charging_dependency_removal,
}
