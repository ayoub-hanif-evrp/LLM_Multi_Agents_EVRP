"""Solution helpers for the classical backbone."""
from __future__ import annotations

from copy import deepcopy

from evrptw_autolab.problem.v2.evaluator import evaluate_solution_v2
from evrptw_autolab.problem.v2.report import EvaluationReportV2
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2, VehicleTypeV2


def default_vehicle_id(spec: ProblemSpecV2) -> str:
    if not spec.vehicle_types:
        raise ValueError("spec has no vehicle types")
    # Prefer BEV when heterogeneous; else first type.
    for vehicle in spec.vehicle_types:
        if vehicle.is_electric and not vehicle.is_hybrid and not vehicle.is_conventional:
            return vehicle.type_id
    for vehicle in spec.vehicle_types:
        if vehicle.is_electric or vehicle.is_hybrid:
            return vehicle.type_id
    return spec.vehicle_types[0].type_id


def vehicle_for_route(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    route_index: int,
) -> VehicleTypeV2:
    type_id = None
    if route_index < len(solution.vehicle_assignments) and solution.vehicle_assignments[route_index]:
        type_id = solution.vehicle_assignments[route_index]
    elif solution.routes and route_index < len(solution.routes) and solution.routes[route_index]:
        type_id = solution.routes[route_index][0].vehicle_type_id
    elif len(spec.vehicle_types) == 1:
        type_id = spec.vehicle_types[0].type_id
    if type_id is None:
        type_id = default_vehicle_id(spec)
    for vehicle in spec.vehicle_types:
        if vehicle.type_id == type_id:
            return vehicle
    raise ValueError(f"unknown vehicle type {type_id!r}")


def empty_route(spec: ProblemSpecV2, vehicle_id: str | None = None) -> list[RouteStopV2]:
    depot = spec.depot_ids[0]
    vid = vehicle_id or default_vehicle_id(spec)
    return [
        RouteStopV2(depot, vehicle_type_id=vid, event="depot"),
        RouteStopV2(depot, vehicle_type_id=vid, event="depot"),
    ]


def clone_solution(solution: SolutionV2) -> SolutionV2:
    return SolutionV2(
        routes=[[deepcopy(s) for s in route] for route in solution.routes],
        vehicle_assignments=list(solution.vehicle_assignments),
        metadata=dict(solution.metadata),
    )


def route_node_ids(route: list[RouteStopV2]) -> list[str]:
    return [s.node_id for s in route]


def make_customer_stop(node_id: str, spec: ProblemSpecV2) -> RouteStopV2:
    node = spec.node_map[node_id]
    if node.kind == "pickup":
        event = "pickup"
    elif node.kind == "delivery":
        event = "delivery"
    else:
        event = "visit"
    return RouteStopV2(node_id, event=event)  # type: ignore[arg-type]


def evaluate(spec: ProblemSpecV2, solution: SolutionV2) -> EvaluationReportV2:
    return evaluate_solution_v2(spec, solution)


def is_better(a: EvaluationReportV2, b: EvaluationReportV2) -> bool:
    """Feasibility-first comparison."""
    if a.feasible != b.feasible:
        return a.feasible and not b.feasible
    if a.feasible and b.feasible:
        ao = float("inf") if a.objective is None else a.objective
        bo = float("inf") if b.objective is None else b.objective
        return ao < bo - 1e-9
    # Both infeasible: fewer hard violations, then lower objective if any.
    if len(a.violations) != len(b.violations):
        return len(a.violations) < len(b.violations)
    ao = float("inf") if a.objective is None else a.objective
    bo = float("inf") if b.objective is None else b.objective
    return ao < bo - 1e-9


def served_request_nodes(spec: ProblemSpecV2) -> list[str]:
    if spec.capabilities.pickup_delivery and spec.requests:
        out: list[str] = []
        for req in spec.requests:
            out.extend([req.pickup_id, req.delivery_id])
        return out
    return [n.id for n in spec.nodes if n.kind == "customer"]
