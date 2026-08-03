"""Deterministic constructive heuristics with bounded charging-station repair."""
from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from chargecegis.problem import Instance, Route, Solution
from chargecegis.propagation import arc_metrics, propagate_route


@dataclass
class ConstructionResult:
    solution: Solution
    feasible: bool
    unserved: list[str] = field(default_factory=list)
    rejection_log: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class ChargingReconstructionConfig:
    max_station_candidates_per_gap: int = 5
    max_inserted_stations_per_route: int = 3
    max_repair_attempts_per_move: int = 30  # kept for backwards compatibility; prefer max_expansions
    beam_width: int = 8
    max_expansions: int = 80


_DEFAULT_CONFIG = ChargingReconstructionConfig()


def _stops_are_feasible(instance: Instance, route: Route) -> bool:
    """Per-stop battery, load, and customer-time-window checks (no depot-return check)."""
    for stop in route.schedule:
        node = instance.nodes[stop.node_id]
        if stop.battery_on_arrival < -1e-6 or stop.battery_on_departure < -1e-6:
            return False
        if stop.battery_on_departure > instance.vehicle.battery_capacity + 1e-6:
            return False
        if stop.cumulative_load > instance.vehicle.freight_capacity + 1e-6:
            return False
        if node.kind == "customer" and stop.service_start > node.due_time + 1e-6:
            return False
    return True


def _route_is_locally_feasible(instance: Instance, route: Route) -> bool:
    if route.node_ids[0] != instance.depot_id or route.node_ids[-1] != instance.depot_id:
        return False
    if not _stops_are_feasible(instance, route):
        return False
    return route.schedule[-1].arrival_time <= instance.depot.due_time + 1e-6


def _strip_to_customers(instance: Instance, sequence: Sequence[str]) -> tuple[str, ...]:
    """Drop depot and station ids, preserving the relative order of customers."""
    return tuple(node_id for node_id in sequence if node_id in instance.customer_ids)


def _nearest_station_detours(instance: Instance, p: str, q: str, limit: int) -> list[tuple[float, str]]:
    """Stations sorted by insertion detour d(p,s)+d(s,q)-d(p,q), nearest first."""
    if limit <= 0 or not instance.station_ids:
        return []
    base = arc_metrics(instance, p, q).distance
    scored = sorted(
        (
            (arc_metrics(instance, p, s).distance + arc_metrics(instance, s, q).distance - base, s)
            for s in instance.station_ids
        ),
        key=lambda item: (item[0], item[1]),
    )
    return scored[:limit]


# A beam candidate is (node_sequence_so_far, customer_skeleton_index_reached, inserted_station_count).
_BeamState = tuple[tuple[str, ...], int, int]


def _beam_search_stations(
    instance: Instance, skeleton: tuple[str, ...], *, vehicle_index: int, config: ChargingReconstructionConfig,
) -> Route | None:
    """Bounded beam search inserting charging stations into ``skeleton`` (depot + customers + depot).

    Each expansion advances one customer-skeleton position, optionally preceded by one of the
    nearest candidate stations for that gap. Infeasible prefixes (negative/over-capacity battery,
    overloaded freight, or a customer served past its time window) are pruned immediately; the
    survivors are ranked by (inserted-station count, distance-so-far) and truncated to
    ``beam_width`` before the next round. The search stops as soon as any beam member reaches the
    final depot feasibly, or once ``max_expansions`` node insertions have been tried.
    """
    beam: list[_BeamState] = [((skeleton[0],), 1, 0)]
    expansions = 0
    while beam and expansions < config.max_expansions:
        frontier: list[_BeamState] = []
        for sequence, skeleton_index, station_count in beam:
            next_node = skeleton[skeleton_index]
            last_node = sequence[-1]
            if expansions >= config.max_expansions:
                break
            expansions += 1
            frontier.append((sequence + (next_node,), skeleton_index + 1, station_count))
            if station_count < config.max_inserted_stations_per_route:
                candidates = _nearest_station_detours(
                    instance, last_node, next_node, config.max_station_candidates_per_gap
                )
                for _, station in candidates:
                    if expansions >= config.max_expansions:
                        break
                    expansions += 1
                    frontier.append((sequence + (station, next_node), skeleton_index + 1, station_count + 1))

        completed: list[Route] = []
        scored: list[tuple[int, float, _BeamState]] = []
        for sequence, skeleton_index, station_count in frontier:
            try:
                route = propagate_route(instance, sequence, vehicle_index=vehicle_index)
            except (KeyError, ValueError):
                continue
            if not _stops_are_feasible(instance, route):
                continue
            if skeleton_index == len(skeleton):
                if _route_is_locally_feasible(instance, route):
                    completed.append(route)
                continue
            distance = route.schedule[-1].traveled_distance
            scored.append((station_count, distance, (sequence, skeleton_index, station_count)))

        if completed:
            return min(completed, key=lambda route: route.schedule[-1].traveled_distance)
        if not scored:
            return None
        scored.sort(key=lambda item: (item[0], item[1]))
        beam = [state for _, _, state in scored[: config.beam_width]]
    return None


def reconstruct_route_charging(
    instance: Instance,
    customer_sequence: Sequence[str],
    *,
    vehicle_index: int,
    config: ChargingReconstructionConfig | None = None,
) -> Route | None:
    """Rebuild a feasible route serving ``customer_sequence`` in order, inserting stations as needed.

    ``customer_sequence`` is treated as a depot-free, station-free ordered list of customers:
    any depot or station ids present in the input are stripped first (customer relative order
    is preserved), so callers may also pass a full route ``node_ids`` tuple directly. The direct
    (station-free) route is tried first; if it already satisfies ``_route_is_locally_feasible`` it
    is returned as-is. Otherwise a bounded beam search (see ``_beam_search_stations``) inserts
    charging stations, certifying feasibility and full recharge via ``propagate_route`` /
    ``LinearFullRechargeModel``. The search is bounded by ``config`` so the candidate space never
    explodes combinatorially with the number of stations.
    """
    config = config or _DEFAULT_CONFIG
    customers = _strip_to_customers(instance, customer_sequence)
    if not customers:
        return None
    skeleton = (instance.depot_id, *customers, instance.depot_id)

    try:
        direct = propagate_route(instance, skeleton, vehicle_index=vehicle_index)
    except (KeyError, ValueError):
        return None
    if _route_is_locally_feasible(instance, direct):
        return direct
    return _beam_search_stations(instance, skeleton, vehicle_index=vehicle_index, config=config)


def repair_charging(
    instance: Instance,
    customers: tuple[str, ...],
    *,
    vehicle_index: int,
    config: ChargingReconstructionConfig | None = None,
) -> Route | None:
    """Backwards-compatible alias for reconstructing a single dedicated route."""
    return reconstruct_route_charging(instance, customers, vehicle_index=vehicle_index, config=config)


def route_distance(route: Route) -> float:
    """Total traveled distance of ``route``, read off its final schedule stop."""
    return route.schedule[-1].traveled_distance if route.schedule else 0.0


def insert_customers_best_fit(
    instance: Instance,
    solution: Solution,
    customers: Sequence[str],
    *,
    config: ChargingReconstructionConfig | None = None,
    rng: random.Random | None = None,
) -> Solution:
    """Greedily insert ``customers`` into the cheapest feasible position, else a new route.

    Customers are processed in a randomized-then-due-time-sorted order (the shuffle only breaks
    ties among equal due times, keeping the schedule deterministic given ``rng``). Each customer
    is tried at every customer-adjacent position of every existing route; the winner is selected
    lexicographically by (insertion distance delta, route index, position), where the delta is
    the rebuilt route's distance minus that route's distance *before* the insertion -- never the
    rebuilt route's absolute distance, which would unfairly penalise inserting into a long route.
    If no existing route can host the customer feasibly, it is placed on its own new dedicated
    route as a fallback. Routes left without customers are dropped and vehicle indices are
    renumbered densely from 0.
    """
    config = config or _DEFAULT_CONFIG
    rng = rng or random.Random()
    ordered = list(customers)
    rng.shuffle(ordered)
    ordered.sort(key=lambda cid: instance.nodes[cid].due_time)

    routes: list[Route] = list(solution.routes)
    for customer in ordered:
        original_distances = [route_distance(route) for route in routes]
        best_key: tuple[float, int, int] | None = None
        best_index: int | None = None
        best_route: Route | None = None
        for index, route in enumerate(routes):
            base_customers = tuple(nid for nid in route.node_ids if nid in instance.customer_ids)
            for position in range(len(base_customers) + 1):
                candidate = base_customers[:position] + (customer,) + base_customers[position:]
                rebuilt = reconstruct_route_charging(
                    instance, candidate, vehicle_index=route.vehicle_index, config=config
                )
                if rebuilt is None:
                    continue
                insertion_delta = route_distance(rebuilt) - original_distances[index]
                key = (insertion_delta, index, position)
                if best_key is None or key < best_key:
                    best_key, best_index, best_route = key, index, rebuilt
        if best_index is not None and best_route is not None:
            routes[best_index] = best_route
        else:
            dedicated = reconstruct_route_charging(
                instance, (customer,), vehicle_index=len(routes), config=config
            )
            if dedicated is not None:
                routes.append(dedicated)

    kept = [route for route in routes if any(nid in instance.customer_ids for nid in route.node_ids)]
    renumbered = tuple(replace(route, vehicle_index=index) for index, route in enumerate(kept))
    return Solution(renumbered, solution.metadata)


def construct_initial_solution(instance: Instance) -> ConstructionResult:
    """Serve earliest-deadline customers in dedicated, one-customer-per-vehicle routes.

    This is the conservative dedicated-route fallback: it favours certified feasibility over
    route quality (and fleet size) and never merges customers onto a shared vehicle. Prefer
    ``construct_merged_initial_solution`` for a fleet-efficient starting point.
    """
    routes: list[Route] = []
    unserved: list[str] = []
    log: list[dict[str, str]] = []
    for customer in sorted(instance.customer_ids, key=lambda cid: (instance.nodes[cid].due_time, cid)):
        route = repair_charging(instance, (customer,), vehicle_index=len(routes))
        if route is None:
            unserved.append(customer)
            log.append({"customer": customer, "reason": "no_station_pattern"})
        else:
            routes.append(route)
    solution = Solution(tuple(routes), {"construction": "dedicated_routes"})
    return ConstructionResult(solution, not unserved, unserved, log)


def construct_merged_initial_solution(
    instance: Instance, *, seed: int = 0, config: ChargingReconstructionConfig | None = None,
) -> ConstructionResult:
    """Deterministically merge customers onto as few vehicles as feasible.

    Customers are visited in ascending (due_time, id) order and inserted one at a time via
    ``insert_customers_best_fit`` (falling back to a new dedicated route only when no existing
    route can host a customer feasibly), using a single seeded RNG for reproducibility. The
    result is a fleet-efficient alternative to ``construct_initial_solution``'s one-route-per-
    customer baseline.
    """
    config = config or _DEFAULT_CONFIG
    rng = random.Random(seed)
    ordered = sorted(instance.customer_ids, key=lambda cid: (instance.nodes[cid].due_time, cid))

    solution = Solution((), {})
    unserved: list[str] = []
    log: list[dict[str, str]] = []
    for customer in ordered:
        solution = insert_customers_best_fit(instance, solution, (customer,), config=config, rng=rng)
        served = {nid for route in solution.routes for nid in route.node_ids}
        if customer not in served:
            unserved.append(customer)
            log.append({"customer": customer, "reason": "no_station_pattern"})

    total_distance = sum(route_distance(route) for route in solution.routes)
    solution = Solution(solution.routes, {
        "construction": "merged",
        "initial_vehicles": len(solution.routes),
        "initial_distance": total_distance,
    })
    feasible = not unserved
    try:
        from chargecegis.feasibility import (
            evaluate_feasibility,  # local import: optional soft check
        )
        feasible = feasible and evaluate_feasibility(instance, solution).feasible
    except ImportError:
        pass
    return ConstructionResult(solution, feasible, unserved, log)
