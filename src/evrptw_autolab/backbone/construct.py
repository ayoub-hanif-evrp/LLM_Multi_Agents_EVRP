"""Deterministic constructive heuristics (no LLM)."""
from __future__ import annotations

import random
from dataclasses import dataclass

from evrptw_autolab.backbone.util import (
    call_scorer,
    candidate_vehicle_ids,
    clone_solution,
    default_vehicle_id,
    empty_route,
    evaluate,
    make_customer_stop,
    note_scorer_call,
    note_selected_move,
    served_request_nodes,
    vehicle_for_route,
)
from evrptw_autolab.problem.v2.route_simulator import simulate_route
from evrptw_autolab.problem.v2.transport import EPSILON, travel_distance
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2, VehicleTypeV2


def _finite_due(node) -> float:
    from evrptw_autolab.backbone.util import finite_due

    return finite_due(float(node.due_time))


def _insertion_features(
    spec: ProblemSpecV2,
    route: list[RouteStopV2],
    index: int,
    node_id: str,
    vehicle: VehicleTypeV2 | None = None,
) -> dict[str, float]:
    """Feature values at one insertion. v1 names keep the historical capacity slack."""
    prev = spec.node_map[route[index - 1].node_id]
    nxt = spec.node_map[route[index].node_id]
    node = spec.node_map[node_id]
    delta = (
        travel_distance(spec, prev, node)
        + travel_distance(spec, node, nxt)
        - travel_distance(spec, prev, nxt)
    )
    due = _finite_due(node)
    ready = float(node.ready_time) if node.ready_time == node.ready_time else 0.0
    vehicle_cap = spec.vehicle_types[0].capacity if spec.vehicle_types else 0.0
    load = sum(spec.node_map[s.node_id].demand for s in route if s.event != "depot")
    slack = float(vehicle_cap) - float(load)
    typed = vehicle
    if typed is None and spec.vehicle_types:
        typed = spec.vehicle_types[0]
    fixed = float(typed.fixed_cost) if typed is not None else 0.0
    rate = float(typed.consumption_rate or 0.0) if typed is not None else 0.0
    has_customer = any(stop.event != "depot" for stop in route)
    return {
        "delta_distance": float(delta),
        "due_time": float(due),
        "ready_time": ready,
        "demand": float(node.demand),
        "capacity_slack": float(slack),
        "vehicle_fixed_cost": fixed,
        "marginal_energy": rate * float(delta),
        "new_route_fixed_cost": 0.0 if has_customer else fixed,
    }


def _insertion_cost(
    spec: ProblemSpecV2,
    route: list[RouteStopV2],
    index: int,
    node_id: str,
    policy: object | None = None,
    vehicle: VehicleTypeV2 | None = None,
) -> float:
    """Cheap insertion score (not a feasibility check). Lower is better."""
    features = _insertion_features(spec, route, index, node_id, vehicle)
    scorer = getattr(policy, "insertion_score", None) if policy is not None else None
    if scorer is None:
        return float(features["delta_distance"]) + 0.001 * float(features["due_time"])
    note_scorer_call(policy, "insertion_score")
    return call_scorer(
        scorer,
        features,
        ("delta_distance", "due_time", "ready_time", "demand", "capacity_slack"),
    )


def _try_insert(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    route_index: int,
    position: int,
    node_id: str,
) -> SolutionV2 | None:
    cand = clone_solution(solution)
    cand.routes[route_index].insert(position, make_customer_stop(node_id, spec))
    report = evaluate(spec, cand)
    # Accept insertion if it does not introduce VISIT duplicates and improves coverage
    # without new capacity/depot parse issues on this partial solution.
    # During construction we allow incomplete coverage; reject capacity/window/depot/parse.
    hard = {v.family for v in report.violations} - {"VISIT", "PAIRING"}
    # BATTERY deferred to energy repair.
    hard -= {"BATTERY", "CHARGE_POLICY"}
    # Duration is hard during construction when the variant publishes a route limit.
    if not spec.capabilities.max_route_duration:
        hard -= {"DURATION"}
    if hard & {"PARSE", "DEPOT", "CAPACITY", "WINDOW", "PRECEDENCE", "DURATION"}:
        return None
    return cand


def _customer_order(spec: ProblemSpecV2, rng: random.Random) -> list[str]:
    customers = served_request_nodes(spec)
    if spec.capabilities.pickup_delivery and spec.requests:
        # Insert pickups first (deliveries handled as pairs).
        return [req.pickup_id for req in spec.requests]
    # Time-window aware: earlier due time first (finite); infinite dues sort last.
    customers = sorted(
        customers,
        key=lambda cid: (_finite_due(spec.node_map[cid]), spec.node_map[cid].ready_time, cid),
    )
    order = list(customers)
    rng.shuffle(order)
    order.sort(key=lambda cid: (_finite_due(spec.node_map[cid]), cid))
    return order


def _initialization_vehicles(spec: ProblemSpecV2) -> list[VehicleTypeV2]:
    """Conventional vehicles first, then rising fixed cost. Feasibility before energy cost."""

    def rank(vehicle: VehicleTypeV2) -> tuple[int, float, str]:
        conventional = 0 if vehicle.is_conventional and not vehicle.is_electric and not vehicle.is_hybrid else 1
        return (conventional, float(vehicle.fixed_cost), vehicle.type_id)

    return sorted(spec.vehicle_types, key=rank)


def _energy_prices(spec: ProblemSpecV2) -> tuple[float, float]:
    prices = spec.metadata.get("energy_prices") or {}
    return float(prices.get("fossil-fuel", 0.0)), float(prices.get("electricity", 0.0))


def _route_energy_cost(spec: ProblemSpecV2, trajectory: list) -> float:
    fossil, electric = _energy_prices(spec)
    if not trajectory:
        return 0.0
    last = trajectory[-1]
    return fossil * float(last.fuel_used) + electric * float(last.electric_used)


def _priced_fleet(spec: ProblemSpecV2) -> bool:
    fossil, electric = _energy_prices(spec)
    return spec.capabilities.heterogeneous_fleet and (fossil > 0.0 or electric > 0.0)


def route_covers_locally(
    spec: ProblemSpecV2,
    route: list[RouteStopV2],
    vehicle: VehicleTypeV2,
) -> tuple[bool, float, float]:
    """Capacity, time windows, and depot return for one route. No whole-solution evaluate."""
    load = 0.0
    for stop in route:
        node = spec.node_map[stop.node_id]
        if node.kind in {"customer", "pickup", "delivery"}:
            load += float(node.demand)
    if vehicle.capacity is not None and load > float(vehicle.capacity) + EPSILON:
        return False, float("inf"), float("inf")
    try:
        traj, errors = simulate_route(spec, route, vehicle)
    except (KeyError, ValueError):
        return False, float("inf"), float("inf")
    if errors:
        return False, float("inf"), float("inf")
    uses_battery = (vehicle.is_electric or vehicle.is_hybrid) and vehicle.battery_capacity is not None
    if uses_battery:
        for state in traj:
            if state.battery_arrival < -EPSILON or state.battery_departure < -EPSILON:
                return False, float("inf"), float("inf")
    if spec.capabilities.time_windows and traj:
        for state in traj:
            node = spec.node_map[state.node_id]
            if node.kind in {"customer", "pickup", "delivery"} and state.service_start > node.due_time + EPSILON:
                return False, float("inf"), float("inf")
        depot = spec.node_map[spec.depot_ids[0]]
        if traj[-1].arrival_time > depot.due_time + EPSILON:
            return False, float("inf"), float("inf")
    distance = float(traj[-1].distance_so_far) if traj else 0.0
    return True, distance, _route_energy_cost(spec, traj)


@dataclass
class _RepairChoice:
    cost: float
    tie: float
    route: int
    pos: int
    opened: str | None
    upgrade: str | None


def _consider_fleet_repairs(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    customer_id: str,
    blocked: list[tuple[int, VehicleTypeV2, float]],
    best: _RepairChoice,
) -> None:
    """Price a larger vehicle on a full route, and a new route, against the native energy cost."""
    demand = float(spec.node_map[customer_id].demand)

    def accept(
        cost: float,
        tie: float,
        route: int,
        pos: int,
        opened: str | None,
        upgrade: str | None,
    ) -> None:
        better = cost < best.cost - 1e-12 or (abs(cost - best.cost) <= 1e-12 and tie < best.tie)
        if not better:
            return
        best.cost = cost
        best.tie = tie
        best.route = route
        best.pos = pos
        best.opened = opened
        best.upgrade = upgrade

    for r_idx, vehicle, base_energy in blocked:
        route = solution.routes[r_idx]
        load = demand
        for stop in route:
            kind = spec.node_map[stop.node_id].kind
            if kind in {"customer", "pickup", "delivery"}:
                load += float(spec.node_map[stop.node_id].demand)
        for alt in spec.vehicle_types:
            if alt.type_id == vehicle.type_id:
                continue
            if alt.capacity is not None and load > float(alt.capacity) + EPSILON:
                continue
            for pos in range(1, len(route)):
                trial = list(route)
                trial.insert(pos, make_customer_stop(customer_id, spec))
                ok, distance, energy = route_covers_locally(spec, trial, alt)
                if not ok:
                    continue
                accept(
                    (alt.fixed_cost - float(vehicle.fixed_cost)) + (energy - base_energy),
                    distance,
                    r_idx,
                    pos,
                    None,
                    alt.type_id,
                )
    for alt in _initialization_vehicles(spec):
        if alt.capacity is not None and demand > float(alt.capacity) + EPSILON:
            continue
        opened = empty_route(spec, alt.type_id)
        opened.insert(1, make_customer_stop(customer_id, spec))
        ok, distance, energy = route_covers_locally(spec, opened, alt)
        if not ok:
            continue
        accept(float(alt.fixed_cost) + energy, distance, -1, -1, alt.type_id, None)


def insert_customer_fast(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    customer_id: str,
    policy: object | None = None,
) -> SolutionV2:
    """Insert one customer using route-local checks. Opens a conventional route when needed."""
    best_route = -1
    best_pos = -1
    best_cost = float("inf")
    best_tie = float("inf")
    best_open: str | None = None
    best_upgrade: str | None = None
    considered: list[tuple[float, int, int]] = []
    node = spec.node_map[customer_id]
    priced = policy is None and _priced_fleet(spec)
    blocked: list[tuple[int, VehicleTypeV2, float]] = []
    priced_options: list[tuple[float, float, int, int]] = []
    for r_idx, route in enumerate(solution.routes):
        try:
            vehicle = vehicle_for_route(spec, solution, r_idx)
        except ValueError:
            continue
        base_ok, _base_distance, base_energy = route_covers_locally(spec, route, vehicle)
        if not base_ok:
            base_energy = 0.0
        local_cost = float("inf")
        local_choice: tuple[float, float, int] | None = None
        for pos in range(1, len(route)):
            trial = list(route)
            trial.insert(pos, make_customer_stop(customer_id, spec))
            ok, distance, energy = route_covers_locally(spec, trial, vehicle)
            if not ok:
                continue
            delta = distance - (0.0 if not base_ok else _base_distance)
            if policy is not None:
                cost = _insertion_cost(spec, route, pos, customer_id, policy=policy, vehicle=vehicle)
            else:
                cost = delta
            considered.append((float(cost), r_idx, pos))
            if cost < local_cost - 1e-12:
                local_cost = cost
                local_choice = (energy - base_energy, delta, pos)
            if cost < best_cost - 1e-12:
                best_cost = cost
                best_tie = delta
                best_route = r_idx
                best_pos = pos
                best_open = None
                best_upgrade = None
        if local_choice is not None and priced:
            energy_delta, delta, pos = local_choice
            priced_options.append((energy_delta, delta, r_idx, pos))
        elif priced:
            blocked.append((r_idx, vehicle, base_energy))
    if priced and priced_options:
        energy_delta, delta, r_idx, pos = min(priced_options)
        best_cost = energy_delta
        best_tie = delta
        best_route = r_idx
        best_pos = pos
        best_open = None
        best_upgrade = None
    elif priced and best_route < 0:
        choice = _RepairChoice(best_cost, best_tie, best_route, best_pos, best_open, best_upgrade)
        _consider_fleet_repairs(spec, solution, customer_id, blocked, choice)
        best_cost = choice.cost
        best_tie = choice.tie
        best_route = choice.route
        best_pos = choice.pos
        best_open = choice.opened
        best_upgrade = choice.upgrade
    scorer = getattr(policy, "insertion_score", None) if policy is not None else None
    referenced = set(getattr(scorer, "referenced_names", ()) or ())
    if "new_route_fixed_cost" in referenced:
        demand = float(node.demand)
        for vehicle in _initialization_vehicles(spec):
            if vehicle.capacity is not None and demand > float(vehicle.capacity) + EPSILON:
                continue
            opened = empty_route(spec, vehicle.type_id)
            trial_route = list(opened)
            trial_route.insert(1, make_customer_stop(customer_id, spec))
            ok, _distance, _energy = route_covers_locally(spec, trial_route, vehicle)
            if not ok:
                continue
            cost = _insertion_cost(spec, opened, 1, customer_id, policy=policy, vehicle=vehicle)
            considered.append((float(cost), 10**6, 0))
            if cost < best_cost - 1e-12:
                best_cost = cost
                best_route = -1
                best_pos = -1
                best_open = vehicle.type_id
    if considered and policy is not None:
        ordered = sorted(considered, key=lambda item: (item[0], item[1], item[2]))
        note_selected_move(
            policy,
            "insertion_score",
            f"{customer_id}:{ordered[0][1]}:{ordered[0][2]}",
            [f"{customer_id}:{item[1]}:{item[2]}" for item in ordered],
        )
    if best_open is not None:
        updated = clone_solution(solution)
        opened = empty_route(spec, best_open)
        opened.insert(1, make_customer_stop(customer_id, spec))
        updated.routes.append(opened)
        updated.vehicle_assignments.append(best_open)
        return updated
    if best_route >= 0:
        updated = clone_solution(solution)
        updated.routes[best_route].insert(best_pos, make_customer_stop(customer_id, spec))
        if best_upgrade is not None:
            updated.vehicle_assignments[best_route] = best_upgrade
            updated.routes[best_route] = [
                RouteStopV2(
                    stop.node_id,
                    best_upgrade,
                    stop.event,
                    stop.charge_amount,
                    stop.charge_technology,
                    stop.target_soc,
                )
                for stop in updated.routes[best_route]
            ]
        return updated
    demand = float(node.demand)
    for vehicle in _initialization_vehicles(spec):
        if vehicle.capacity is not None and demand > float(vehicle.capacity) + EPSILON:
            continue
        route = empty_route(spec, vehicle.type_id)
        route.insert(1, make_customer_stop(customer_id, spec))
        ok, _distance, _energy = route_covers_locally(spec, route, vehicle)
        if not ok:
            continue
        updated = clone_solution(solution)
        updated.routes.append(route)
        updated.vehicle_assignments.append(vehicle.type_id)
        return updated
    fallback = default_vehicle_id(spec)
    route = empty_route(spec, fallback)
    route.insert(1, make_customer_stop(customer_id, spec))
    updated = clone_solution(solution)
    updated.routes.append(route)
    updated.vehicle_assignments.append(fallback)
    return updated


def _construct_heterogeneous(
    spec: ProblemSpecV2,
    rng: random.Random,
    policy: object | None,
) -> SolutionV2:
    """Place every customer before search. Whole-solution evaluates were the 15s bottleneck."""
    vehicle_id = _initialization_vehicles(spec)[0].type_id
    solution = SolutionV2(routes=[empty_route(spec, vehicle_id)], vehicle_assignments=[vehicle_id])
    for customer_id in _customer_order(spec, rng):
        solution = insert_customer_fast(spec, solution, customer_id, policy=policy)
    # Drop the unused seed route when every customer opened its own route.
    if len(solution.routes) > 1 and len(solution.routes[0]) == 2:
        solution.routes = solution.routes[1:]
        solution.vehicle_assignments = solution.vehicle_assignments[1:]
    solution.metadata["construction"] = "heterogeneous_route_local"
    return solution


def _construct_route_local(
    spec: ProblemSpecV2,
    rng: random.Random,
    policy: object | None,
) -> SolutionV2:
    """Insert with route-local checks. Used when a full-solution evaluate is too slow.

    Battery-infeasible single-customer routes are left for energy repair. The
    small-instance constructor is unchanged.
    """
    vehicle_id = default_vehicle_id(spec)
    solution = SolutionV2(routes=[empty_route(spec, vehicle_id)], vehicle_assignments=[vehicle_id])
    for customer_id in _customer_order(spec, rng):
        solution = insert_customer_fast(spec, solution, customer_id, policy=policy)
    if len(solution.routes) > 1 and len(solution.routes[0]) == 2:
        solution.routes = solution.routes[1:]
        solution.vehicle_assignments = solution.vehicle_assignments[1:]
    solution.metadata["construction"] = "route_local_large"
    return solution


def construct_greedy(
    spec: ProblemSpecV2,
    rng: random.Random,
    policy: object | None = None,
) -> SolutionV2:
    """Cheapest feasible insertion (TW/capacity); battery repaired later."""
    if spec.capabilities.heterogeneous_fleet and not (
        spec.capabilities.pickup_delivery and spec.requests
    ):
        return _construct_heterogeneous(spec, rng, policy)
    n_customers = sum(1 for node in spec.nodes if node.kind == "customer")
    if n_customers > 20 and not (spec.capabilities.pickup_delivery and spec.requests):
        return _construct_route_local(spec, rng, policy)
    vehicle_id = default_vehicle_id(spec)
    solution = SolutionV2(routes=[empty_route(spec, vehicle_id)], vehicle_assignments=[vehicle_id])

    if spec.capabilities.pickup_delivery and spec.requests:
        return _construct_pd(spec, rng, solution, vehicle_id)

    for customer_id in _customer_order(spec, rng):
        best: SolutionV2 | None = None
        best_cost = float("inf")
        best_at = ""
        considered: list[tuple[float, int, int]] = []
        for r_idx, route in enumerate(solution.routes):
            for pos in range(1, len(route)):
                cost = _insertion_cost(spec, route, pos, customer_id, policy=policy)
                trial = _try_insert(spec, solution, r_idx, pos, customer_id)
                if trial is None:
                    continue
                considered.append((float(cost), r_idx, pos))
                if cost < best_cost - 1e-12:
                    best_cost = cost
                    best = trial
                    best_at = f"{customer_id}:{r_idx}:{pos}"
        if considered:
            ordered = sorted(considered, key=lambda item: (item[0], item[1], item[2]))
            note_selected_move(
                policy,
                "insertion_score",
                best_at or f"{customer_id}:{ordered[0][1]}:{ordered[0][2]}",
                [f"{customer_id}:{item[1]}:{item[2]}" for item in ordered],
            )
        if best is None:
            # Open a new route; try cheaper vehicle types first on heterogeneous fleets.
            trial = None
            for vid in candidate_vehicle_ids(spec):
                new_route = empty_route(spec, vid)
                new_route.insert(1, make_customer_stop(customer_id, spec))
                cand = clone_solution(solution)
                cand.routes.append(new_route)
                cand.vehicle_assignments.append(vid)
                report = evaluate(spec, cand)
                hard = {v.family for v in report.violations} - {
                    "VISIT",
                    "PAIRING",
                    "BATTERY",
                    "CHARGE_POLICY",
                }
                if not spec.capabilities.max_route_duration:
                    hard -= {"DURATION"}
                if hard & {"PARSE", "DEPOT", "CAPACITY", "WINDOW", "FLEET", "DURATION"}:
                    continue
                trial = cand
                break
            if trial is None:
                new_route = empty_route(spec, vehicle_id)
                new_route.insert(1, make_customer_stop(customer_id, spec))
                trial = clone_solution(solution)
                trial.routes.append(new_route)
                trial.vehicle_assignments.append(vehicle_id)
            solution = trial
        else:
            solution = best
    solution.metadata["construction"] = "cheapest_insertion"
    return solution


def _construct_pd(
    spec: ProblemSpecV2,
    rng: random.Random,
    solution: SolutionV2,
    vehicle_id: str,
) -> SolutionV2:
    """Insert each pickup–delivery pair into the cheapest joint positions."""
    requests = list(spec.requests)
    requests.sort(key=lambda r: (spec.node_map[r.pickup_id].due_time, r.request_id))
    rng.shuffle(requests)
    requests.sort(key=lambda r: (spec.node_map[r.pickup_id].due_time, r.request_id))

    for req in requests:
        best: SolutionV2 | None = None
        best_cost = float("inf")
        for r_idx, route in enumerate(solution.routes):
            # Positions for pickup then delivery after it.
            for ppos in range(1, len(route)):
                for dpos in range(ppos + 1, len(route) + 1):
                    cand = clone_solution(solution)
                    cand.routes[r_idx].insert(ppos, make_customer_stop(req.pickup_id, spec))
                    # delivery index shifts by +1 after pickup insert
                    cand.routes[r_idx].insert(dpos, make_customer_stop(req.delivery_id, spec))
                    report = evaluate(spec, cand)
                    hard = {v.family for v in report.violations} - {
                        "VISIT",
                        "PAIRING",
                        "BATTERY",
                        "CHARGE_POLICY",
                        "DURATION",
                    }
                    if hard & {"PARSE", "DEPOT", "CAPACITY", "WINDOW", "PRECEDENCE"}:
                        continue
                    # Cost: rough distance of both inserts.
                    cost = 0.0
                    rt = cand.routes[r_idx]
                    for i in range(1, len(rt)):
                        cost += travel_distance(
                            spec, spec.node_map[rt[i - 1].node_id], spec.node_map[rt[i].node_id]
                        )
                    if cost < best_cost:
                        best_cost = cost
                        best = cand
        if best is None:
            route = empty_route(spec, vehicle_id)
            route.insert(1, make_customer_stop(req.pickup_id, spec))
            route.insert(2, make_customer_stop(req.delivery_id, spec))
            solution = clone_solution(solution)
            solution.routes.append(route)
            solution.vehicle_assignments.append(vehicle_id)
        else:
            solution = best
    solution.metadata["construction"] = "pd_pair_insertion"
    return solution
