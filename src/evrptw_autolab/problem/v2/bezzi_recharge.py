"""Minimum-cost partial recharge plans for a fixed Bezzi route.

The published objective (Felipe et al. 2014; Ceselli, Felipe, Ortuño, Righini,
Tirado 2021) is recharge cost, not distance:

    cost = sum over positive recharges (f + gamma_h * energy_charged)

Depot technology 0 is the cheap overnight recharge (rho_0 = 0). Station visits
choose one available technology. Charge amounts are integer energy units when
the instance energy matrix is integral, which it is in this benchmark.

Published solution XML does not store charge amounts. For a fixed node sequence
the route cost is the optimal recharge plan, subject to battery capacity and
maximum route duration.
"""
from __future__ import annotations

from dataclasses import dataclass

from evrptw_autolab.problem.v2.transport import energy_required, travel_time
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, VehicleTypeV2

_INF = 1e18


@dataclass(frozen=True, slots=True)
class _Label:
    cost: float
    time: float
    plan: tuple[tuple[str | None, int], ...]


def _pareto(labels: list[_Label]) -> list[_Label]:
    labels.sort(key=lambda lab: (lab.cost, lab.time))
    kept: list[_Label] = []
    best_time = _INF
    for lab in labels:
        if lab.time < best_time - 1e-7:
            kept.append(lab)
            best_time = lab.time
    return kept


def plan_bezzi_recharges(
    spec: ProblemSpecV2,
    stops: list[RouteStopV2],
    vehicle: VehicleTypeV2,
) -> list[RouteStopV2] | None:
    """Return stops annotated with charge amounts, or None if no feasible plan exists."""
    battery_cap = vehicle.battery_capacity
    if battery_cap is None:
        return None
    capacity = int(round(float(battery_cap)))
    if capacity <= 0 or abs(float(battery_cap) - capacity) > 1e-6:
        return None
    techs: dict[str, dict[str, float]] = vehicle.metadata.get("charging_techs") or {}
    if not techs:
        return None
    fixed = float(spec.metadata.get("fixed_recharge_cost") or 0.0)
    max_time = vehicle.metadata.get("max_travel_time")
    limit = float(max_time) if max_time is not None else None
    nodes = spec.node_map

    leg_energy: list[int] = []
    leg_time: list[float] = []
    for index in range(1, len(stops)):
        prev = nodes[stops[index - 1].node_id]
        nxt = nodes[stops[index].node_id]
        raw = energy_required(spec, prev, nxt, vehicle)
        energy = int(round(raw))
        if abs(raw - energy) > 1e-4:
            return None
        leg_energy.append(energy)
        leg_time.append(travel_time(spec, prev, nxt, vehicle))

    # Labels are keyed by battery after the decision at the current stop, before the next leg.
    frontier: dict[int, list[_Label]] = {0: [_Label(0.0, 0.0, ())]}

    for index, stop in enumerate(stops):
        node = nodes[stop.node_id]
        can_charge = index == 0 or node.kind == "station"
        available: list[tuple[str, float, float]] = []
        if can_charge:
            choices = list(node.charge_technologies) or (["0"] if index == 0 else [])
            for tech in choices:
                params = techs.get(str(tech))
                if params is None:
                    continue
                available.append((str(tech), float(params["gamma"]), float(params["rho"])))
            if not available and index == 0 and "0" in techs:
                params = techs["0"]
                available.append(("0", float(params["gamma"]), float(params["rho"])))

        updated: dict[int, list[_Label]] = {}
        for battery, labels in frontier.items():
            for lab in labels:
                options: list[tuple[str | None, int, float, float]] = [(None, 0, 0.0, 0.0)]
                if can_charge and available and stop.charge_amount is None and stop.target_soc is None:
                    options = []
                    for tech, gamma, rho in available:
                        room = capacity - battery
                        for delta in range(0, room + 1):
                            extra_cost = (fixed + gamma * delta) if delta > 0 else 0.0
                            options.append((tech if delta > 0 else None, delta, extra_cost, rho * delta))
                elif stop.charge_amount is not None:
                    delta = int(round(stop.charge_amount))
                    chosen_tech = stop.charge_technology
                    gamma = (
                        float(techs.get(str(chosen_tech), techs.get("0", {})).get("gamma", 0.0))
                        if chosen_tech
                        else 0.0
                    )
                    rho = float(techs.get(str(chosen_tech), {}).get("rho", 0.0)) if chosen_tech else 0.0
                    options = [
                        (chosen_tech, delta, (fixed + gamma * delta) if delta > 0 else 0.0, rho * delta)
                    ]

                for chosen_tech, delta, extra_cost, extra_time in options:
                    charged = battery + delta
                    if charged > capacity:
                        continue
                    cost = lab.cost + extra_cost
                    time = lab.time + extra_time + node.service_time
                    plan = lab.plan + ((chosen_tech, delta),)
                    if index == len(stops) - 1:
                        if limit is not None and time > limit + 1e-6:
                            continue
                        bucket = updated.setdefault(charged, [])
                        bucket.append(_Label(cost, time, plan))
                        continue
                    need = leg_energy[index]
                    if charged < need:
                        continue
                    arrive = charged - need
                    travel = leg_time[index]
                    bucket = updated.setdefault(arrive, [])
                    bucket.append(_Label(cost, time + travel, plan))
        frontier = {bat: _pareto(labs) for bat, labs in updated.items() if labs}
        if not frontier:
            return None

    best: _Label | None = None
    for labels in frontier.values():
        for lab in labels:
            if best is None or lab.cost < best.cost - 1e-9 or (
                abs(lab.cost - best.cost) <= 1e-9 and lab.time < best.time
            ):
                best = lab
    if best is None or len(best.plan) != len(stops):
        return None

    annotated: list[RouteStopV2] = []
    for stop, decision in zip(stops, best.plan, strict=True):
        plan_tech, delta = decision
        if delta <= 0:
            annotated.append(stop)
            continue
        annotated.append(
            RouteStopV2(
                node_id=stop.node_id,
                vehicle_type_id=stop.vehicle_type_id,
                event="charge" if stop.event == "visit" else stop.event,
                charge_amount=float(delta),
                charge_technology=plan_tech,
                target_soc=None,
            )
        )
    return annotated
