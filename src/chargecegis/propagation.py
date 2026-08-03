"""Deterministic time, load, and energy propagation."""
from __future__ import annotations

from math import hypot

from chargecegis.charging import LinearFullRechargeModel
from chargecegis.problem import ArcMetrics, Instance, Route, ScheduleStop


def arc_metrics(instance: Instance, left: str, right: str) -> ArcMetrics:
    a, b = instance.nodes[left], instance.nodes[right]
    distance = hypot(a.coordinates[0] - b.coordinates[0], a.coordinates[1] - b.coordinates[1])
    energy = distance * instance.vehicle.consumption_rate
    return ArcMetrics(distance, distance / instance.vehicle.velocity, energy,
                      energy <= instance.vehicle.battery_capacity + 1e-6)


def propagate_route(instance: Instance, node_ids: tuple[str, ...], *, vehicle_index: int = 0,
                    charging_model: LinearFullRechargeModel | None = None) -> Route:
    if not node_ids:
        raise ValueError("Route must not be empty")
    model = charging_model or LinearFullRechargeModel()
    vehicle = instance.vehicle
    time = distance = load = 0.0
    battery = vehicle.initial_soc
    stops: list[ScheduleStop] = []
    for index, node_id in enumerate(node_ids):
        node = instance.nodes[node_id]
        if index:
            arc = arc_metrics(instance, node_ids[index - 1], node_id)
            distance += arc.distance
            time += arc.travel_time
            battery -= arc.energy
        arrival, arrival_battery = time, battery
        start = max(arrival, node.ready_time) if node.kind in {"customer", "station"} else arrival
        waiting = start - arrival
        charged = duration = 0.0
        if node.kind == "customer":
            load += node.demand
            completion = start + node.service_duration
        elif node.kind == "station":
            decision = model.full_recharge(vehicle, arrival_battery)
            charged, duration, battery = (
                decision.energy_charged, decision.duration, decision.battery_on_departure
            )
            completion = start + duration
        else:
            completion = start
        time = completion
        next_energy = (arc_metrics(instance, node_id, node_ids[index + 1]).energy
                       if index + 1 < len(node_ids) else None)
        stops.append(ScheduleStop(
            node_id, distance, arrival, waiting, start, completion, time, load, arrival_battery,
            charged, battery, next_energy, node.due_time - start,
            battery - (next_energy or 0.0), duration,
        ))
    return Route(vehicle_index, node_ids, tuple(stops))
