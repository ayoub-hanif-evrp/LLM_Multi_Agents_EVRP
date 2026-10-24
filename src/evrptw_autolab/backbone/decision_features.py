"""Features that can differ across real insertion or removal candidates.

v1 capacity slack still uses the first vehicle type. These v4 values use the
candidate route and its assigned vehicle. They are not passed to a v1 scorer.
"""
from __future__ import annotations

from evrptw_autolab.problem.v2.route_simulator import simulate_route
from evrptw_autolab.problem.v2.transport import energy_required, travel_distance, travel_time
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, VehicleTypeV2


def _duration(spec: ProblemSpecV2, route: list[RouteStopV2], vehicle: VehicleTypeV2) -> float:
    total = 0.0
    nodes = spec.node_map
    for left, right in zip(route, route[1:], strict=False):
        total += travel_time(spec, nodes[left.node_id], nodes[right.node_id], vehicle)
    return total


def _length(spec: ProblemSpecV2, route: list[RouteStopV2]) -> float:
    total = 0.0
    nodes = spec.node_map
    for left, right in zip(route, route[1:], strict=False):
        total += travel_distance(spec, nodes[left.node_id], nodes[right.node_id])
    return total


def insertion_features_v4(
    spec: ProblemSpecV2,
    route: list[RouteStopV2],
    index: int,
    node_id: str,
    vehicle: VehicleTypeV2,
) -> dict[str, float]:
    """Cheap position features. Lower insertion scores are better."""
    nodes = spec.node_map
    prev = nodes[route[index - 1].node_id]
    nxt = nodes[route[index].node_id]
    node = nodes[node_id]
    delta = travel_distance(spec, prev, node) + travel_distance(spec, node, nxt) - travel_distance(spec, prev, nxt)
    added_time = (
        travel_time(spec, prev, node, vehicle)
        + travel_time(spec, node, nxt, vehicle)
        - travel_time(spec, prev, nxt, vehicle)
    )
    customers = [stop for stop in route if stop.event != "depot"]
    load = sum(float(nodes[stop.node_id].demand) for stop in customers) + float(node.demand)
    capacity = float(vehicle.capacity) if vehicle.capacity is not None else 0.0
    has_customer = bool(customers)
    trial = list(route)
    trial.insert(index, RouteStopV2(node_id, vehicle.type_id, "visit"))
    return {
        "delta_distance": float(delta),
        "delta_travel_time": float(added_time),
        "route_load_slack_after_insertion": capacity - load,
        "route_customer_count": float(len(customers)),
        "new_vehicle_fixed_cost": 0.0 if has_customer else float(vehicle.fixed_cost),
        "incremental_energy_cost": _incremental_energy_cost(spec, prev, node, nxt, vehicle, float(delta)),
        "battery_margin": battery_margin(spec, trial, vehicle),
    }


def _incremental_energy_cost(
    spec: ProblemSpecV2,
    prev,
    node,
    nxt,
    vehicle: VehicleTypeV2,
    delta_distance: float,
) -> float:
    """Added fuel or electricity cost of replacing one arc. Hybrid vehicles return 0."""
    prices = spec.metadata.get("energy_prices") or {}
    fossil = float(prices.get("fossil-fuel", 0.0))
    electric = float(prices.get("electricity", 0.0))
    pure_ice = vehicle.is_conventional and not vehicle.is_electric and not vehicle.is_hybrid
    if pure_ice:
        rate = float(vehicle.metadata.get("fuel_consumption_rate") or 0.0)
        return delta_distance * rate * fossil
    if vehicle.is_electric and not vehicle.is_hybrid:
        added = (
            energy_required(spec, prev, node, vehicle)
            + energy_required(spec, node, nxt, vehicle)
            - energy_required(spec, prev, nxt, vehicle)
        )
        return float(added) * electric
    return 0.0


def battery_margin(spec: ProblemSpecV2, route: list[RouteStopV2], vehicle: VehicleTypeV2) -> float:
    """Lowest arrival battery on the trial route. A pure ICE vehicle has no battery, so the value is 0."""
    if vehicle.is_conventional and not vehicle.is_electric and not vehicle.is_hybrid:
        return 0.0
    try:
        trajectory, errors = simulate_route(spec, route, vehicle)
    except (KeyError, ValueError):
        return -1.0
    if errors or not trajectory:
        return -1.0
    return float(min(state.battery_arrival for state in trajectory))


def edited_route_features(
    spec: ProblemSpecV2,
    before: list[RouteStopV2],
    after: list[RouteStopV2],
    vehicle: VehicleTypeV2,
) -> dict[str, float]:
    """Features for a pickup-delivery insertion. Distance and energy use the whole edited route."""
    delta = _length(spec, after) - _length(spec, before)
    added_time = _duration(spec, after, vehicle) - _duration(spec, before, vehicle)
    customers = [stop for stop in before if stop.event != "depot"]
    load = sum(float(spec.node_map[stop.node_id].demand) for stop in after if stop.event != "depot")
    capacity = float(vehicle.capacity) if vehicle.capacity is not None else 0.0
    return {
        "delta_distance": float(delta),
        "delta_travel_time": float(added_time),
        "route_load_slack_after_insertion": capacity - load,
        "route_customer_count": float(len(customers)),
        "new_vehicle_fixed_cost": 0.0 if customers else float(vehicle.fixed_cost),
        "incremental_energy_cost": _route_energy_cost(spec, after, vehicle) - _route_energy_cost(spec, before, vehicle),
        "battery_margin": battery_margin(spec, after, vehicle),
    }


def _route_energy_cost(spec: ProblemSpecV2, route: list[RouteStopV2], vehicle: VehicleTypeV2) -> float:
    prices = spec.metadata.get("energy_prices") or {}
    fossil = float(prices.get("fossil-fuel", 0.0))
    electric = float(prices.get("electricity", 0.0))
    pure_ice = vehicle.is_conventional and not vehicle.is_electric and not vehicle.is_hybrid
    total = 0.0
    nodes = spec.node_map
    for left, right in zip(route, route[1:], strict=False):
        if pure_ice:
            rate = float(vehicle.metadata.get("fuel_consumption_rate") or 0.0)
            total += travel_distance(spec, nodes[left.node_id], nodes[right.node_id]) * rate * fossil
        elif vehicle.is_electric and not vehicle.is_hybrid:
            total += energy_required(spec, nodes[left.node_id], nodes[right.node_id], vehicle) * electric
    return float(total)


def marginal_removal_distance(spec: ProblemSpecV2, route: list[RouteStopV2], node_ids: set[str]) -> float:
    """Distance saved by deleting every named stop. Pickup and delivery stay together."""
    full = _length(spec, route)
    kept = [stop for stop in route if stop.event == "depot" or stop.node_id not in node_ids]
    reduced = _length(spec, kept) if len(kept) >= 2 else 0.0
    return float(full - reduced)


def time_window_width(spec: ProblemSpecV2, node_id: str) -> float:
    node = spec.node_map[node_id]
    due = float(node.due_time)
    if due != due or due in (float("inf"), float("-inf")):
        due = 1_000_000.0
    ready = float(node.ready_time) if node.ready_time == node.ready_time else 0.0
    return max(0.0, due - ready)
