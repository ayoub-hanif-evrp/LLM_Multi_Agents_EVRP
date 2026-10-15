"""Deterministic route state propagation for ProblemSpecV2."""
from __future__ import annotations

from evrptw_autolab.problem.v2.charging import resolve_charge
from evrptw_autolab.problem.v2.report import StopStateV2
from evrptw_autolab.problem.v2.transport import energy_required, travel_distance, travel_time
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, VehicleTypeV2


def simulate_route(
    spec: ProblemSpecV2,
    stops: list[RouteStopV2],
    vehicle: VehicleTypeV2,
) -> tuple[list[StopStateV2], list[str]]:
    """Propagate time/load/battery. Never invents missing recharge decisions."""
    if not stops:
        raise ValueError("route must not be empty")
    nodes = spec.node_map
    time = 0.0
    load = 0.0
    travelled = 0.0
    fuel_used = 0.0
    electric_used = 0.0
    battery_cap = vehicle.battery_capacity
    pure_icev = vehicle.is_conventional and not vehicle.is_electric and not vehicle.is_hybrid
    charge_errors: list[str] = []
    if pure_icev:
        battery = 0.0
    elif spec.capabilities.multiple_charge_technologies:
        # Bezzi: battery starts empty unless the solution states an explicit depot charge.
        battery = 0.0
        if all(stop.charge_amount is None and stop.target_soc is None for stop in stops):
            charge_errors.append("missing_charge_decisions")
    else:
        battery = float(battery_cap) if battery_cap is not None else 0.0
    trajectory: list[StopStateV2] = []
    fuel_rate = float(vehicle.metadata.get("fuel_consumption_rate") or 0.0)
    elec_rate = float(vehicle.metadata.get("energy_consumption_rate") or vehicle.consumption_rate or 0.0)

    for index, stop in enumerate(stops):
        if stop.node_id not in nodes:
            raise KeyError(f"unknown node id {stop.node_id!r}")
        node = nodes[stop.node_id]
        if index:
            prev = nodes[stops[index - 1].node_id]
            dist = travel_distance(spec, prev, node)
            travelled += dist
            time += travel_time(spec, prev, node, vehicle)
            if pure_icev:
                fuel_used += dist * fuel_rate
            elif vehicle.is_hybrid:
                # Battery-first PHEV: electric until SoC is exhausted, then fuel.
                need = dist * elec_rate
                available = max(0.0, battery)
                take = min(available, need)
                battery -= take
                electric_used += take
                if need > take + 1e-9 and elec_rate > 0:
                    fuel_used += ((need - take) / elec_rate) * fuel_rate
                elif need > take + 1e-9:
                    fuel_used += dist * fuel_rate
            elif vehicle.is_electric:
                used = energy_required(spec, prev, node, vehicle)
                battery -= used
                electric_used += used

        arrival = time
        arrival_battery = battery
        # Waiting for time windows on serviceable stops.
        if node.kind in {"customer", "pickup", "delivery", "station"}:
            start = max(arrival, node.ready_time)
        else:
            start = arrival

        charged = 0.0
        tech = None
        if node.kind in {"customer", "pickup", "delivery"}:
            load += node.demand
            departure = start + node.service_time
        elif node.kind == "station" or (
            index == 0
            and node.kind == "depot"
            and spec.capabilities.multiple_charge_technologies
            and stop.charge_amount is not None
        ):
            if vehicle.is_conventional and not vehicle.is_electric and not vehicle.is_hybrid:
                charge_errors.append(f"conventional_vehicle_at_station:{node.id}")
                departure = start
            else:
                decision = resolve_charge(spec, vehicle, node, stop, arrival_battery)
                charged = decision.energy_charged
                battery = decision.battery_departure
                tech = decision.technology
                for err in decision.errors:
                    charge_errors.append(f"{node.id}:{err}")
                departure = start + decision.duration + node.service_time
        else:
            departure = start

        time = departure
        trajectory.append(
            StopStateV2(
                node_id=node.id,
                arrival_time=arrival,
                service_start=start,
                departure_time=departure,
                load=load,
                battery_arrival=arrival_battery,
                battery_departure=battery,
                energy_charged=charged,
                distance_so_far=travelled,
                charge_technology=tech,
                fuel_used=fuel_used,
                electric_used=electric_used,
            )
        )
    return trajectory, charge_errors
