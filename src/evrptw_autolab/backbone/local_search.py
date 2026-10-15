"""Deterministic local-search neighborhoods."""
from __future__ import annotations

from evrptw_autolab.backbone.util import (
    clone_solution,
    default_vehicle_id,
    evaluate,
    is_better,
    make_customer_stop,
)
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2


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


def relocate_improve(spec: ProblemSpecV2, solution: SolutionV2, *, max_passes: int = 3) -> SolutionV2:
    """Relocate customer/pickup/delivery nodes to cheaper feasible positions."""
    if spec.capabilities.pickup_delivery and spec.requests:
        return relocate_pairs(spec, solution, max_passes=max_passes)

    current = clone_solution(solution)
    current_report = evaluate(spec, current)
    fallback = default_vehicle_id(spec)
    for _ in range(max_passes):
        improved = False
        for r_idx, route in enumerate(current.routes):
            for i in range(1, len(route) - 1):
                if not _is_request_node(spec, route[i].node_id):
                    continue
                node_id = route[i].node_id
                base = clone_solution(current)
                del base.routes[r_idx][i]
                _drop_empty_routes(base, fallback)
                for rr, rt in enumerate(base.routes):
                    for pos in range(1, len(rt)):
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


def relocate_pairs(spec: ProblemSpecV2, solution: SolutionV2, *, max_passes: int = 3) -> SolutionV2:
    """Relocate pickup-delivery pairs as atomic units."""
    current = clone_solution(solution)
    current_report = evaluate(spec, current)
    fallback = default_vehicle_id(spec)
    for _ in range(max_passes):
        improved = False
        for req in spec.requests:
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


def two_opt_improve(spec: ProblemSpecV2, solution: SolutionV2) -> SolutionV2:
    """Intra-route 2-opt on customer sequences (keeps depots fixed)."""
    if spec.capabilities.pickup_delivery:
        return solution
    current = clone_solution(solution)
    current_report = evaluate(spec, current)
    for r_idx, route in enumerate(current.routes):
        n = len(route)
        if n < 5:
            continue
        improved = True
        while improved:
            improved = False
            for i in range(1, n - 2):
                for j in range(i + 1, n - 1):
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
