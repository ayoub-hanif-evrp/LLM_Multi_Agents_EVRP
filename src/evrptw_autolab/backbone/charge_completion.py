"""Optimizer-side charging-plan completion.

The trusted evaluator never invents charge amounts. Solvers and reference-validation
helpers call this module to annotate routes with explicit recharge decisions.
"""
from __future__ import annotations

import time

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
    drop_idle_stations: bool = False,
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
    return plan_bezzi_recharges(spec, stops, vehicle, drop_idle_stations=drop_idle_stations)


def complete_solution_charges(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    drop_idle_stations: bool = True,
    deadline: float | None = None,
) -> SolutionV2:
    """Annotate every Bezzi route with a fresh recharge plan. No-op for other families.

    Always clears prior charge annotations before planning so structural edits
    (station insert/removal, ALNS) cannot leave stale amounts/technologies.
    A route the DP cannot charge is left unspecified and listed in
    ``metadata['charge_completion_failed_routes']``. That is not a successful plan.
    """
    if not spec.capabilities.multiple_charge_technologies:
        return solution
    out = clone_solution(solution)
    failed: list[int] = []
    for index, route in enumerate(out.routes):
        try:
            vehicle = vehicle_for_route(spec, out, index)
        except ValueError:
            failed.append(index)
            continue
        cleared = [
            RouteStopV2(
                node_id=stop.node_id,
                vehicle_type_id=stop.vehicle_type_id,
                event="visit" if stop.event == "charge" else stop.event,
            )
            for stop in route
        ]
        if deadline is not None and time.monotonic() > deadline:
            break
        planned = plan_bezzi_recharges(
            spec,
            cleared,
            vehicle,
            drop_idle_stations=drop_idle_stations,
            deadline=deadline,
        )
        if planned is None:
            failed.append(index)
            out.routes[index] = cleared
        else:
            out.routes[index] = planned
    out.metadata["charge_completion_failed_routes"] = failed
    out.metadata["charge_completion"] = "bezzi_dp_failed" if failed else "bezzi_dp"
    return out
