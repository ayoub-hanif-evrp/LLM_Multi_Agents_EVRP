"""Helpers shared by construction and operators."""

from __future__ import annotations

from evocharge.domain.instance import Instance
from evocharge.domain.route import Route
from evocharge.domain.solution import Solution
from evocharge.solver.feasibility import evaluate_feasibility, evaluate_objective
from evocharge.solver.propagation import propagate_route


def customer_sequence_of(route: Route, instance: Instance) -> tuple[str, ...]:
    customers = set(instance.customer_ids)
    return tuple(nid for nid in route.node_ids if nid in customers)


def remove_customers_from_solution(
    instance: Instance,
    solution: Solution,
    to_remove: set[str],
    *,
    cache=None,
    bounds=None,
    profiler=None,
) -> Solution:
    """Remove customers and reconstruct charging on remaining routes (parent process)."""
    from evocharge.solver.charging_repair import repair_charging

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
    return Solution(
        routes=tuple(
            Route(vehicle_index=i, node_ids=r.node_ids, schedule=r.schedule, metadata=r.metadata)
            for i, r in enumerate(new_routes)
        ),
        metadata=dict(solution.metadata),
    )


def strip_stations(node_ids: tuple[str, ...], instance: Instance) -> tuple[str, ...]:
    stations = set(instance.station_ids)
    return tuple(nid for nid in node_ids if nid not in stations)


def route_is_internally_feasible(instance: Instance, route: Route) -> bool:
    """Check a single route ignoring global customer coverage of other customers."""
    sol = Solution(routes=(route,))
    report = evaluate_feasibility(instance, sol)
    local_customers = set(customer_sequence_of(route, instance))
    return not (
        report.invalid_node_visits
        or report.capacity_violations
        or report.time_window_violations
        or report.battery_violations
        or report.charging_violations
        or report.depot_violations
        or report.unreachable_arcs
        or any(c in local_customers for c in report.duplicate_customers)
    )


def build_and_check_route(
    instance: Instance,
    node_ids: tuple[str, ...],
    *,
    vehicle_index: int = 0,
) -> Route | None:
    if not node_ids or node_ids[0] != instance.depot_id or node_ids[-1] != instance.depot_id:
        return None
    route = propagate_route(instance, node_ids, vehicle_index=vehicle_index)
    if route_is_internally_feasible(instance, route):
        return route
    return None


def solution_objective(instance: Instance, solution: Solution):
    report = evaluate_feasibility(instance, solution)
    return evaluate_objective(instance, solution, report), report
