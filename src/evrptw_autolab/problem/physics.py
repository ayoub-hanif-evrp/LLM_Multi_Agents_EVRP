"""Exact Schneider distance, time, energy, and full-recharge arithmetic."""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from evrptw_autolab.problem.types import EVRPTWInstance, Node, VehicleSpec

EPSILON = 1e-6


@dataclass(frozen=True)
class StopState:
    node_id: str
    arrival_time: float
    service_start: float
    departure_time: float
    load: float
    battery_arrival: float
    battery_departure: float
    energy_charged: float
    distance_so_far: float


@dataclass(frozen=True)
class ChargeDecision:
    energy_charged: float
    duration: float
    battery_departure: float


def distance(left: Node, right: Node) -> float:
    return hypot(left.x - right.x, left.y - right.y)


def travel_time(left: Node, right: Node, vehicle: VehicleSpec) -> float:
    return distance(left, right) / vehicle.velocity


def energy_required(left: Node, right: Node, vehicle: VehicleSpec) -> float:
    return distance(left, right) * vehicle.consumption_rate


def full_recharge(vehicle: VehicleSpec, battery_on_arrival: float) -> ChargeDecision:
    energy = max(0.0, vehicle.battery_capacity - battery_on_arrival)
    duration = energy * vehicle.inverse_refuel_rate
    return ChargeDecision(energy, duration, vehicle.battery_capacity)


def validate_full_recharge(
    vehicle: VehicleSpec, battery_on_arrival: float, energy_charged: float
) -> list[str]:
    errors: list[str] = []
    expected = max(0.0, vehicle.battery_capacity - battery_on_arrival)
    if abs(energy_charged - expected) > EPSILON:
        errors.append("partial_recharge_not_allowed")
    if battery_on_arrival < -EPSILON:
        errors.append("negative_battery_on_arrival")
    return errors


def propagate_route(instance: EVRPTWInstance, node_ids: list[str]) -> list[StopState]:
    if not node_ids:
        raise ValueError("route must not be empty")
    nodes = instance.node_map
    vehicle = instance.vehicle
    time = 0.0
    load = 0.0
    travelled = 0.0
    battery = vehicle.start_soc
    stops: list[StopState] = []
    for index, node_id in enumerate(node_ids):
        node = nodes[node_id]
        if index:
            prev = nodes[node_ids[index - 1]]
            travelled += distance(prev, node)
            time += travel_time(prev, node, vehicle)
            battery -= energy_required(prev, node, vehicle)
        arrival, arrival_battery = time, battery
        start = max(arrival, node.ready_time) if node.kind in {"customer", "station"} else arrival
        charged = 0.0
        if node.kind == "customer":
            load += node.demand
            departure = start + node.service_time
        elif node.kind == "station":
            decision = full_recharge(vehicle, arrival_battery)
            charged, battery = decision.energy_charged, decision.battery_departure
            departure = start + decision.duration
        else:
            departure = start
        time = departure
        stops.append(
            StopState(
                node_id, arrival, start, departure, load, arrival_battery, battery, charged, travelled
            )
        )
    return stops
