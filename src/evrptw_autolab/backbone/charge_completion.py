"""Optimizer-side charging-plan completion.

The trusted evaluator never invents charge amounts. Solvers and reference-validation
helpers call this module to annotate routes with explicit recharge decisions.
"""
from __future__ import annotations

from evrptw_autolab.backbone.util import clone_solution, vehicle_for_route
from evrptw_autolab.problem.v2.bezzi_recharge import plan_bezzi_recharges
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2


def route_needs_charge_completion(spec: ProblemSpecV2, stops: list[RouteStopV2]) -> bool:
    if not spec.capabilities.multiple_charge_technologies:
        return False
    return all(stop.charge_amount is None and stop.target_soc is None for stop in stops)


def complete_route_charges(
    spec: ProblemSpecV2,
    stops: list[RouteStopV2],
    *,
    vehicle_type_id: str | None = None,
) -> list[RouteStopV2] | None:
    """Return stops with explicit charge amounts, or None if no feasible plan exists."""
    if not route_needs_charge_completion(spec, stops):
        return list(stops)
    vehicle = None
    if vehicle_type_id is not None:
        vehicle = next((v for v in spec.vehicle_types if v.type_id == vehicle_type_id), None)
    if vehicle is None and len(spec.vehicle_types) == 1:
        vehicle = spec.vehicle_types[0]
    if vehicle is None:
        return None
    return plan_bezzi_recharges(spec, stops, vehicle)


def complete_solution_charges(spec: ProblemSpecV2, solution: SolutionV2) -> SolutionV2:
    """Annotate every Bezzi route with a fresh recharge plan. No-op for other families.

    Always clears prior charge annotations before planning so structural edits
    (station insert/removal, ALNS) cannot leave stale amounts/technologies.
    """
    if not spec.capabilities.multiple_charge_technologies:
        return solution
    out = clone_solution(solution)
    for index, route in enumerate(out.routes):
        try:
            vehicle = vehicle_for_route(spec, out, index)
        except ValueError:
            continue
        cleared = [
            RouteStopV2(
                node_id=stop.node_id,
                vehicle_type_id=stop.vehicle_type_id,
                event=stop.event,
            )
            for stop in route
        ]
        planned = plan_bezzi_recharges(spec, cleared, vehicle)
        if planned is not None:
            out.routes[index] = planned
        else:
            out.routes[index] = cleared
    out.metadata["charge_completion"] = "bezzi_dp"
    return out
