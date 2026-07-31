"""Deterministic route schedule propagation for EVRPTW."""

from __future__ import annotations

from evocharge.distances.matrix import DistanceMatrix
from evocharge.distances.provider import DistanceProvider, default_provider
from evocharge.domain.charging import ChargingModel, default_charging_model
from evocharge.domain.instance import Instance
from evocharge.domain.route import Route, ScheduleStop


def propagate_route(
    instance: Instance,
    node_ids: tuple[str, ...],
    *,
    vehicle_index: int = 0,
    full_recharge_at_stations: bool = True,
    charging_amounts: dict[int, float] | None = None,
    provider: DistanceProvider | None = None,
    charging_model: ChargingModel | None = None,
) -> Route:
    """Propagate times, load, and battery along a fixed node sequence.

    Provisional charging policy (recorded in the dataset contract):
    at station nodes, default is full recharge to battery capacity ``Q``.
    """
    if not node_ids:
        raise ValueError("Route must contain at least one node")

    matrix = DistanceMatrix(instance, provider or default_provider())
    charger = charging_model or default_charging_model()
    vehicle = instance.vehicle
    amounts = charging_amounts or {}

    stops: list[ScheduleStop] = []
    cumulative_distance = 0.0
    time = 0.0
    load = 0.0
    battery = float(vehicle.initial_soc)

    for idx, node_id in enumerate(node_ids):
        node = instance.nodes[node_id]
        if idx == 0:
            arrival = 0.0
        else:
            prev_id = node_ids[idx - 1]
            arc = matrix.get(prev_id, node_id)
            cumulative_distance += arc.distance
            arrival = time + arc.travel_time
            battery -= arc.energy

        battery_on_arrival = battery
        waiting = 0.0
        energy_charged = 0.0
        charging_duration = 0.0

        if node.kind == "customer":
            service_start = max(arrival, node.ready_time)
            waiting = max(0.0, service_start - arrival)
            service_completion = service_start + node.service_duration
            load += node.demand
            departure = service_completion
        elif node.kind == "station":
            service_start = max(arrival, node.ready_time)
            waiting = max(0.0, service_start - arrival)
            if idx in amounts:
                energy_charged = float(amounts[idx])
            elif full_recharge_at_stations:
                energy_charged = max(0.0, vehicle.battery_capacity - battery_on_arrival)
            charging_duration = charger.charging_duration(
                vehicle, battery_on_arrival, energy_charged
            )
            service_completion = service_start + charging_duration
            departure = service_completion
            battery = battery_on_arrival + energy_charged
        else:
            service_start = arrival
            if idx in amounts:
                energy_charged = float(amounts[idx])
                charging_duration = charger.charging_duration(
                    vehicle, battery_on_arrival, energy_charged
                )
                service_completion = service_start + charging_duration
                battery = battery_on_arrival + energy_charged
                departure = service_completion
            else:
                service_completion = arrival
                departure = arrival

        energy_required_next: float | None = None
        if idx + 1 < len(node_ids):
            energy_required_next = matrix.get(node_id, node_ids[idx + 1]).energy

        stops.append(
            ScheduleStop(
                node_id=node_id,
                traveled_distance=cumulative_distance,
                arrival_time=arrival,
                waiting_time=waiting,
                service_start=service_start,
                service_completion=service_completion,
                departure_time=departure,
                cumulative_load=load,
                battery_on_arrival=battery_on_arrival,
                energy_charged=energy_charged,
                battery_on_departure=battery,
                energy_required_next=energy_required_next,
                time_slack=node.due_time - service_start,
                energy_slack=battery - (energy_required_next or 0.0),
                charging_duration=charging_duration,
            )
        )
        time = departure

    return Route(vehicle_index=vehicle_index, node_ids=node_ids, schedule=tuple(stops))
