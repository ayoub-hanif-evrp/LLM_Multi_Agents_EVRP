"""Solution helpers for the classical backbone."""
from __future__ import annotations

from copy import deepcopy

from evrptw_autolab.problem.v2.evaluator import evaluate_solution_v2
from evrptw_autolab.problem.v2.report import EvaluationReportV2
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2, VehicleTypeV2

FINITE_DUE_SENTINEL = 1_000_000.0


def finite_due(due: float) -> float:
    """Map an infinite or missing due time to a finite sentinel."""
    value = float(due)
    if value != value or value in (float("inf"), float("-inf")):
        return FINITE_DUE_SENTINEL
    return value


def default_vehicle_id(spec: ProblemSpecV2) -> str:
    if not spec.vehicle_types:
        raise ValueError("spec has no vehicle types")
    if not spec.capabilities.heterogeneous_fleet:
        return spec.vehicle_types[0].type_id
    # Prefer the cheapest fixed-cost type that can serve at least one customer demand.
    candidates = sorted(spec.vehicle_types, key=lambda v: (v.fixed_cost, v.type_id))
    demands = [n.demand for n in spec.nodes if n.kind in {"customer", "pickup"} and n.demand > 0]
    max_demand = max(demands) if demands else 0.0
    for vehicle in candidates:
        if vehicle.capacity is None or vehicle.capacity + 1e-9 >= max_demand:
            return vehicle.type_id
    return candidates[0].type_id


def candidate_vehicle_ids(spec: ProblemSpecV2) -> list[str]:
    """Vehicle types to try when opening or reassigning a route."""
    if not spec.capabilities.heterogeneous_fleet:
        return [default_vehicle_id(spec)]
    return [v.type_id for v in sorted(spec.vehicle_types, key=lambda v: (v.fixed_cost, v.type_id))]


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
    """Feasibility-first comparison using lexicographic objective keys."""
    if a.feasible != b.feasible:
        return a.feasible and not b.feasible
    if a.feasible and b.feasible:
        return tuple(a.objective_key) < tuple(b.objective_key)
    if len(a.violations) != len(b.violations):
        return len(a.violations) < len(b.violations)
    return tuple(a.objective_key) < tuple(b.objective_key)


def note_scorer_call(policy: object | None, name: str) -> None:
    """Count scorer invocations when the policy exposes a ``call_counts`` dict."""
    if policy is None:
        return
    counts = getattr(policy, "call_counts", None)
    if isinstance(counts, dict):
        counts[name] = int(counts.get(name, 0)) + 1


def call_scorer(scorer: object, values: dict[str, float], legacy: tuple[str, ...]) -> float:
    """Pass the features the loaded expression declares. Extra features stay unused."""
    names = getattr(scorer, "parameter_names", None) or legacy
    try:
        args = tuple(float(values[str(name)]) for name in names)
    except KeyError as error:
        raise TypeError(f"scorer feature {error} was not provided") from error
    return float(scorer(*args))  # type: ignore[operator]


def note_decision(policy: object | None, event: dict[str, object]) -> None:
    """Append one compact repair event. The log stops at 64 entries."""
    if policy is None:
        return
    log = getattr(policy, "decision_trace", None)
    if not isinstance(log, list) or len(log) >= 64:
        return
    log.append(dict(event))


def note_selected_move(policy: object | None, kind: str, chosen: str, order: list[str]) -> None:
    """Record one selected move and the candidate order that produced it."""
    if policy is None:
        return
    log = getattr(policy, "selected_moves", None)
    if not isinstance(log, list) or len(log) >= 16:
        return
    log.append({"kind": kind, "chosen": chosen, "order": list(order[:8])})


def served_request_nodes(spec: ProblemSpecV2) -> list[str]:
    if spec.capabilities.pickup_delivery and spec.requests:
        out: list[str] = []
        for req in spec.requests:
            out.extend([req.pickup_id, req.delivery_id])
        return out
    return [n.id for n in spec.nodes if n.kind == "customer"]
