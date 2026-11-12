"""Route-local screening for ALNS repair without whole-solution evaluation."""

from __future__ import annotations

from evrptw_autolab.backbone.perf_counters import bump
from evrptw_autolab.problem.v2.route_simulator import simulate_route
from evrptw_autolab.problem.v2.transport import EPSILON
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2, VehicleTypeV2


def peak_route_load(spec: ProblemSpecV2, route: list[RouteStopV2]) -> float:
    load = 0.0
    peak = 0.0
    for stop in route:
        if stop.event == "depot":
            continue
        load += float(spec.node_map[stop.node_id].demand)
        peak = max(peak, load)
    return peak


def screen_repair_route(
    spec: ProblemSpecV2,
    route: list[RouteStopV2],
    vehicle: VehicleTypeV2,
    *,
    allow_battery_debt: bool = True,
) -> tuple[bool, float]:
    """Capacity + windows (+ optional battery) for one edited route.

    ALNS repair intentionally allows temporary battery infeasibility so stations can
    be inserted later. Pass ``allow_battery_debt=True`` to preserve that contract.
    """
    bump("route_screens")
    capacity = float(vehicle.capacity) if vehicle.capacity is not None else 0.0
    if capacity > 0.0 and peak_route_load(spec, route) > capacity + EPSILON:
        return False, float("inf")
    try:
        traj, errors = simulate_route(spec, route, vehicle)
    except (KeyError, ValueError):
        return False, float("inf")
    bump("route_simulations")
    if errors:
        if not allow_battery_debt:
            return False, float("inf")
        # Charging is repaired later; only reject structural station misuse here.
        if any(item.startswith("conventional_vehicle_at_station") for item in errors):
            return False, float("inf")
    if not allow_battery_debt:
        uses_battery = (vehicle.is_electric or vehicle.is_hybrid) and vehicle.battery_capacity is not None
        if uses_battery and traj:
            for state in traj:
                if state.battery_arrival < -EPSILON or state.battery_departure < -EPSILON:
                    return False, float("inf")
    if spec.capabilities.time_windows and traj:
        for state in traj:
            node = spec.node_map[state.node_id]
            if node.kind in {"customer", "pickup", "delivery"} and state.service_start > node.due_time + EPSILON:
                return False, float("inf")
        depot = spec.node_map[spec.depot_ids[0]]
        if traj[-1].arrival_time > depot.due_time + EPSILON:
            return False, float("inf")
    distance = float(traj[-1].distance_so_far) if traj else 0.0
    return True, distance


def replace_route(solution: SolutionV2, route_index: int, route: list[RouteStopV2]) -> SolutionV2:
    """Build a trial solution that shares unchanged routes and stop objects."""
    bump("clones")
    routes = list(solution.routes)
    routes[route_index] = route
    return SolutionV2(
        routes=routes,
        vehicle_assignments=list(solution.vehicle_assignments),
        metadata=dict(solution.metadata),
    )
