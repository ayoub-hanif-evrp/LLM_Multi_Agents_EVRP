"""Deterministic local-search neighborhoods."""
from __future__ import annotations

import time

from evrptw_autolab.backbone.util import (
    clone_solution,
    default_vehicle_id,
    evaluate,
    is_better,
    make_customer_stop,
)
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2


def _past_deadline(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() > deadline


def _is_request_node(spec: ProblemSpecV2, node_id: str) -> bool:
    kind = spec.node_map[node_id].kind
    return kind in {"customer", "pickup", "delivery"}


def _sync_assignments(solution: SolutionV2, fallback: str) -> None:
    """Keep vehicle_assignments aligned 1:1 with routes after structural edits."""
    if len(solution.vehicle_assignments) > len(solution.routes):
        solution.vehicle_assignments = solution.vehicle_assignments[: len(solution.routes)]
    while len(solution.vehicle_assignments) < len(solution.routes):
        solution.vehicle_assignments.append(fallback)


def _drop_empty_routes(solution: SolutionV2, fallback: str) -> None:
    kept_routes: list[list[RouteStopV2]] = []
    kept_assign: list[str] = []
    for idx, route in enumerate(solution.routes):
        if len(route) <= 2:
            continue
        kept_routes.append(route)
        if idx < len(solution.vehicle_assignments):
            kept_assign.append(solution.vehicle_assignments[idx])
        else:
            kept_assign.append(fallback)
    solution.routes = kept_routes
    solution.vehicle_assignments = kept_assign
    _sync_assignments(solution, fallback)


def relocate_improve(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    max_passes: int = 3,
    deadline: float | None = None,
) -> SolutionV2:
    """Relocate customer/pickup/delivery nodes to cheaper feasible positions."""
    if spec.capabilities.pickup_delivery and spec.requests:
        return relocate_pairs(spec, solution, max_passes=max_passes, deadline=deadline)

    current = clone_solution(solution)
    current_report = evaluate(spec, current)
    fallback = default_vehicle_id(spec)
    for _ in range(max_passes):
        if _past_deadline(deadline):
            break
        improved = False
        for r_idx, route in enumerate(current.routes):
            if _past_deadline(deadline):
                break
            for i in range(1, len(route) - 1):
                if not _is_request_node(spec, route[i].node_id):
                    continue
                node_id = route[i].node_id
                base = clone_solution(current)
                del base.routes[r_idx][i]
                _drop_empty_routes(base, fallback)
                for rr, rt in enumerate(base.routes):
                    for pos in range(1, len(rt)):
                        if _past_deadline(deadline):
                            break
                        trial = clone_solution(base)
                        trial.routes[rr].insert(pos, make_customer_stop(node_id, spec))
                        _sync_assignments(trial, fallback)
                        report = evaluate(spec, trial)
                        if is_better(report, current_report):
                            current = trial
                            current_report = report
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
        if not improved:
            break
    return current


def relocate_pairs(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    max_passes: int = 3,
    deadline: float | None = None,
) -> SolutionV2:
    """Relocate pickup-delivery pairs as atomic units."""
    current = clone_solution(solution)
    current_report = evaluate(spec, current)
    fallback = default_vehicle_id(spec)
    for _ in range(max_passes):
        if _past_deadline(deadline):
            break
        improved = False
        for req in spec.requests:
            if _past_deadline(deadline):
                break
            # Find current route containing the pair.
            src = None
            for r_idx, route in enumerate(current.routes):
                ids = {s.node_id for s in route}
                if req.pickup_id in ids and req.delivery_id in ids:
                    src = r_idx
                    break
            if src is None:
                continue
            base = clone_solution(current)
            base.routes[src] = [
                s
                for s in base.routes[src]
                if s.node_id not in {req.pickup_id, req.delivery_id} or s.event == "depot"
            ]
            # Rebuild depot ends.
            route = base.routes[src]
            if len(route) <= 2:
                del base.routes[src]
                if src < len(base.vehicle_assignments):
                    del base.vehicle_assignments[src]
            _drop_empty_routes(base, fallback)
            # Try reinsertion positions on every route.
            targets = list(range(len(base.routes)))
            # Also allow opening a new route.
            for rr in targets + [-1]:
                if rr == -1:
                    trial = clone_solution(base)
                    from evrptw_autolab.backbone.util import empty_route

                    nr = empty_route(spec, fallback)
                    nr.insert(1, make_customer_stop(req.pickup_id, spec))
                    nr.insert(2, make_customer_stop(req.delivery_id, spec))
                    trial.routes.append(nr)
                    trial.vehicle_assignments.append(fallback)
                    report = evaluate(spec, trial)
                    if is_better(report, current_report):
                        current = trial
                        current_report = report
                        improved = True
                        break
                    continue
                route = base.routes[rr]
                for ppos in range(1, len(route)):
                    for dpos in range(ppos + 1, len(route) + 1):
                        trial = clone_solution(base)
                        trial.routes[rr].insert(ppos, make_customer_stop(req.pickup_id, spec))
                        trial.routes[rr].insert(dpos, make_customer_stop(req.delivery_id, spec))
                        _sync_assignments(trial, fallback)
                        report = evaluate(spec, trial)
                        if is_better(report, current_report):
                            current = trial
                            current_report = report
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
        if not improved:
            break
    return current


def two_opt_improve(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    deadline: float | None = None,
) -> SolutionV2:
    """Intra-route 2-opt on customer sequences (keeps depots fixed)."""
    if spec.capabilities.pickup_delivery:
        return solution
    current = clone_solution(solution)
    current_report = evaluate(spec, current)
    for r_idx, route in enumerate(current.routes):
        if _past_deadline(deadline):
            break
        n = len(route)
        if n < 5:
            continue
        improved = True
        while improved:
            if _past_deadline(deadline):
                break
            improved = False
            for i in range(1, n - 2):
                for j in range(i + 1, n - 1):
                    if _past_deadline(deadline):
                        break
                    trial = clone_solution(current)
                    segment = trial.routes[r_idx][i : j + 1]
                    trial.routes[r_idx][i : j + 1] = list(reversed(segment))
                    report = evaluate(spec, trial)
                    if is_better(report, current_report):
                        current = trial
                        current_report = report
                        improved = True
                        break
                if improved:
                    break
    return current


def merge_routes_improve(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    max_passes: int = 4,
    deadline: float | None = None,
) -> SolutionV2:
    """Try consolidating pairs of routes to cut fleet size / duration / cost."""
    if spec.capabilities.pickup_delivery and spec.requests:
        return _merge_pd_routes(spec, solution, max_passes=max_passes, deadline=deadline)

    from evrptw_autolab.backbone.charge_completion import complete_solution_charges
    from evrptw_autolab.backbone.energy_repair import repair_energy
    from evrptw_autolab.backbone.nonlinear_charge import optimize_solution_partial_charges

    current = clone_solution(solution)
    current_report = evaluate(spec, current)
    fallback = default_vehicle_id(spec)
    for _ in range(max_passes):
        if _past_deadline(deadline):
            break
        improved = False
        # Prefer merging short routes first (excessive splits).
        order = sorted(range(len(current.routes)), key=lambda i: len(current.routes[i]))
        attempts = 0
        for a_pos, a_idx in enumerate(order):
            if _past_deadline(deadline):
                break
            for b_idx in order[a_pos + 1 :]:
                if _past_deadline(deadline) or attempts >= 40:
                    break
                if a_idx >= len(current.routes) or b_idx >= len(current.routes):
                    continue
                route_b = current.routes[b_idx]
                customers_a = [
                    s.node_id
                    for s in current.routes[a_idx][1:-1]
                    if _is_request_node(spec, s.node_id)
                ]
                customers_b = [
                    s.node_id for s in route_b[1:-1] if _is_request_node(spec, s.node_id)
                ]
                if not customers_b or len(customers_a) + len(customers_b) > 12:
                    continue
                attempts += 1
                assign = (
                    current.vehicle_assignments[a_idx]
                    if a_idx < len(current.vehicle_assignments)
                    else fallback
                )
                depot = current.routes[a_idx][0].node_id
                for order_ids in (
                    customers_a + customers_b,
                    customers_b + customers_a,
                    customers_a + list(reversed(customers_b)),
                ):
                    trial = clone_solution(current)
                    merged = [
                        RouteStopV2(depot, vehicle_type_id=assign, event="depot"),
                        *[make_customer_stop(nid, spec) for nid in order_ids],
                        RouteStopV2(depot, vehicle_type_id=assign, event="depot"),
                    ]
                    trial.routes[a_idx] = merged
                    del trial.routes[b_idx]
                    if b_idx < len(trial.vehicle_assignments):
                        del trial.vehicle_assignments[b_idx]
                    _sync_assignments(trial, fallback)
                    trial = repair_energy(spec, trial, max_inserts=12, deadline=deadline)
                    trial = complete_solution_charges(spec, trial)
                    trial = optimize_solution_partial_charges(spec, trial)
                    report = evaluate(spec, trial)
                    if is_better(report, current_report):
                        current = trial
                        current_report = report
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
        if not improved:
            break
    return current


def _merge_pd_routes(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    max_passes: int = 3,
    deadline: float | None = None,
) -> SolutionV2:
    """Merge two PD routes by moving all pairs from B into A when improving."""
    from evrptw_autolab.backbone.energy_repair import repair_energy

    current = clone_solution(solution)
    current_report = evaluate(spec, current)
    fallback = default_vehicle_id(spec)
    for _ in range(max_passes):
        if _past_deadline(deadline) or len(current.routes) < 2:
            break
        improved = False
        n_routes = len(current.routes)
        for a_idx in range(n_routes):
            for b_idx in range(n_routes):
                if a_idx == b_idx or _past_deadline(deadline):
                    continue
                ids_b = {s.node_id for s in current.routes[b_idx]}
                pairs = [
                    req
                    for req in spec.requests
                    if req.pickup_id in ids_b and req.delivery_id in ids_b
                ]
                if not pairs or len(pairs) > 4:
                    continue
                trial = clone_solution(current)
                drop = {n for req in pairs for n in (req.pickup_id, req.delivery_id)}
                trial.routes[b_idx] = [
                    s
                    for s in trial.routes[b_idx]
                    if s.node_id not in drop or s.event == "depot"
                ]
                dst = a_idx
                if len(trial.routes[b_idx]) <= 2:
                    del trial.routes[b_idx]
                    if b_idx < len(trial.vehicle_assignments):
                        del trial.vehicle_assignments[b_idx]
                    if a_idx > b_idx:
                        dst = a_idx - 1
                for req in pairs:
                    route = trial.routes[dst]
                    ppos = max(1, len(route) - 1)
                    trial.routes[dst].insert(ppos, make_customer_stop(req.pickup_id, spec))
                    trial.routes[dst].insert(ppos + 1, make_customer_stop(req.delivery_id, spec))
                _sync_assignments(trial, fallback)
                trial = repair_energy(spec, trial, max_inserts=12, deadline=deadline)
                report = evaluate(spec, trial)
                if is_better(report, current_report):
                    current = trial
                    current_report = report
                    improved = True
                    break
            if improved:
                break
        if not improved:
            break
    return current
