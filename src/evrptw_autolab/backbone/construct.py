"""Deterministic constructive heuristics (no LLM)."""
from __future__ import annotations

import random

from evrptw_autolab.backbone.util import (
    clone_solution,
    default_vehicle_id,
    empty_route,
    evaluate,
    make_customer_stop,
    served_request_nodes,
)
from evrptw_autolab.problem.v2.transport import travel_distance
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2


def _insertion_cost(
    spec: ProblemSpecV2,
    route: list[RouteStopV2],
    index: int,
    node_id: str,
    policy: object | None = None,
) -> float:
    """Cheap insertion score (not a feasibility check). Lower is better."""
    prev = spec.node_map[route[index - 1].node_id]
    nxt = spec.node_map[route[index].node_id]
    node = spec.node_map[node_id]
    delta = (
        travel_distance(spec, prev, node)
        + travel_distance(spec, node, nxt)
        - travel_distance(spec, prev, nxt)
    )
    scorer = getattr(policy, "insertion_score", None) if policy is not None else None
    if scorer is None:
        return delta
    vehicle_cap = spec.vehicle_types[0].capacity if spec.vehicle_types else 0.0
    # Rough load on route (sum demands of request nodes).
    load = sum(spec.node_map[s.node_id].demand for s in route if s.event != "depot")
    slack = float(vehicle_cap) - float(load)
    return float(
        scorer(
            float(delta),
            float(node.due_time),
            float(node.ready_time),
            float(node.demand),
            float(slack),
        )
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
    hard -= {"BATTERY", "CHARGE_POLICY", "DURATION"}
    if hard & {"PARSE", "DEPOT", "CAPACITY", "WINDOW", "PRECEDENCE"}:
        return None
    return cand


def _customer_order(spec: ProblemSpecV2, rng: random.Random) -> list[str]:
    customers = served_request_nodes(spec)
    if spec.capabilities.pickup_delivery and spec.requests:
        # Insert pickups first (deliveries handled as pairs).
        return [req.pickup_id for req in spec.requests]
    # Time-window aware: earlier due time first, tie-break by id for determinism.
    customers = sorted(
        customers,
        key=lambda cid: (spec.node_map[cid].due_time, spec.node_map[cid].ready_time, cid),
    )
    # Light deterministic shuffle keyed by rng for diversity across seeds.
    order = list(customers)
    rng.shuffle(order)
    # Re-sort primarily by due time after shuffle of equal-due groups only:
    order.sort(key=lambda cid: (spec.node_map[cid].due_time, cid))
    return order


def construct_greedy(
    spec: ProblemSpecV2,
    rng: random.Random,
    policy: object | None = None,
) -> SolutionV2:
    """Cheapest feasible insertion (TW/capacity); battery repaired later."""
    vehicle_id = default_vehicle_id(spec)
    solution = SolutionV2(routes=[empty_route(spec, vehicle_id)], vehicle_assignments=[vehicle_id])

    if spec.capabilities.pickup_delivery and spec.requests:
        return _construct_pd(spec, rng, solution, vehicle_id)

    for customer_id in _customer_order(spec, rng):
        best: SolutionV2 | None = None
        best_cost = float("inf")
        for r_idx, route in enumerate(solution.routes):
            for pos in range(1, len(route)):
                cost = _insertion_cost(spec, route, pos, customer_id, policy=policy)
                trial = _try_insert(spec, solution, r_idx, pos, customer_id)
                if trial is None:
                    continue
                if cost < best_cost - 1e-12:
                    best_cost = cost
                    best = trial
        if best is None:
            # Open a new route.
            new_route = empty_route(spec, vehicle_id)
            new_route.insert(1, make_customer_stop(customer_id, spec))
            trial = clone_solution(solution)
            trial.routes.append(new_route)
            trial.vehicle_assignments.append(vehicle_id)
            report = evaluate(spec, trial)
            hard = {v.family for v in report.violations} - {"VISIT", "PAIRING", "BATTERY", "CHARGE_POLICY", "DURATION"}
            if hard & {"PARSE", "DEPOT", "CAPACITY", "WINDOW"}:
                # Last resort: still keep the dedicated route (repair later).
                pass
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
