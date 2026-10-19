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

import time as _time
from dataclasses import dataclass
from typing import Literal

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


def _bare_stop(stop: RouteStopV2) -> RouteStopV2:
    """Drop charge annotations so the DP can choose a fresh plan for this node."""
    event = "visit" if stop.event == "charge" else stop.event
    return RouteStopV2(node_id=stop.node_id, vehicle_type_id=stop.vehicle_type_id, event=event)


def _canonicalize(stop: RouteStopV2, *, kind: str, index: int, tech: str | None, delta: int) -> RouteStopV2:
    """Write an explicit charge decision. A zero amount is a no-op, not a missing plan."""
    if delta > 0:
        event: Literal["visit", "pickup", "delivery", "charge", "depot"] = (
            "depot" if kind == "depot" or stop.event == "depot" else "charge"
        )
        return RouteStopV2(
            node_id=stop.node_id,
            vehicle_type_id=stop.vehicle_type_id,
            event=event,
            charge_amount=float(delta),
            charge_technology=tech,
        )
    if kind == "station":
        return RouteStopV2(
            node_id=stop.node_id,
            vehicle_type_id=stop.vehicle_type_id,
            event="visit",
            charge_amount=0.0,
        )
    if kind == "depot" and index == 0:
        return RouteStopV2(
            node_id=stop.node_id,
            vehicle_type_id=stop.vehicle_type_id,
            event="depot",
            charge_amount=0.0,
        )
    return RouteStopV2(
        node_id=stop.node_id,
        vehicle_type_id=stop.vehicle_type_id,
        event="depot" if kind == "depot" else stop.event,
    )


def plan_bezzi_recharges(
    spec: ProblemSpecV2,
    stops: list[RouteStopV2],
    vehicle: VehicleTypeV2,
    *,
    drop_idle_stations: bool = False,
    deadline: float | None = None,
) -> list[RouteStopV2] | None:
    """Return a fully specified route, or None if no feasible recharge plan exists.

    Every retained station has an explicit ``charge_amount`` (zero means the
    vehicle visits and does not recharge). When ``drop_idle_stations`` is set,
    a zero-recharge station is removed only if the shortened route still has a
    feasible plan whose recharge cost is no higher.
    """
    planned = _plan_fixed_sequence(spec, stops, vehicle, deadline=deadline)
    if planned is None or not drop_idle_stations:
        return None if planned is None else planned[0]
    current, cost = planned
    for _ in range(len(current)):
        idle = [
            index
            for index, stop in enumerate(current)
            if spec.node_map[stop.node_id].kind == "station" and float(stop.charge_amount or 0.0) <= 0.0
        ]
        removed = False
        for index in idle:
            reduced = [_bare_stop(stop) for pos, stop in enumerate(current) if pos != index]
            trial = _plan_fixed_sequence(spec, reduced, vehicle, deadline=deadline)
            if trial is None or trial[1] > cost + 1e-6:
                continue
            current, cost = trial
            removed = True
            break
        if not removed:
            break
    return current


def _plan_fixed_sequence(
    spec: ProblemSpecV2,
    stops: list[RouteStopV2],
    vehicle: VehicleTypeV2,
    *,
    deadline: float | None = None,
) -> tuple[list[RouteStopV2], float] | None:
    """Optimal recharge plan for one fixed node sequence."""
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
        if deadline is not None and _time.monotonic() > deadline:
            return None
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
            if deadline is not None and _time.monotonic() > deadline:
                return None
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
    for index, (stop, decision) in enumerate(zip(stops, best.plan, strict=True)):
        plan_tech, delta = decision
        annotated.append(
            _canonicalize(
                stop,
                kind=nodes[stop.node_id].kind,
                index=index,
                tech=plan_tech,
                delta=delta,
            )
        )
    return annotated, best.cost
