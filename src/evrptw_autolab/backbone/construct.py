"""Deterministic constructive heuristics (no LLM)."""
from __future__ import annotations

import random

from evrptw_autolab.backbone.util import (
    candidate_vehicle_ids,
    clone_solution,
    default_vehicle_id,
    empty_route,
    evaluate,
    make_customer_stop,
    note_scorer_call,
    served_request_nodes,
)
from evrptw_autolab.problem.v2.transport import travel_distance
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2


def _finite_due(node) -> float:
    from evrptw_autolab.components.interfaces import normalize_due_time

    return normalize_due_time(float(node.due_time))


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
        # Prefer insertions that keep time-window slack when windows exist.
        due = _finite_due(node)
        return float(delta) + 0.001 * due
    note_scorer_call(policy, "insertion_score")
    vehicle_cap = spec.vehicle_types[0].capacity if spec.vehicle_types else 0.0
    # Rough load on route (sum demands of request nodes).
    load = sum(spec.node_map[s.node_id].demand for s in route if s.event != "depot")
    slack = float(vehicle_cap) - float(load)
    return float(
        scorer(
            float(delta),
            _finite_due(node),
            float(node.ready_time) if node.ready_time == node.ready_time else 0.0,
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
