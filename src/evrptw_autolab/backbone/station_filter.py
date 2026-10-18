"""Trusted station checks. A generated score ranks only the stations that survive."""
from __future__ import annotations

from dataclasses import dataclass, replace

from evrptw_autolab.backbone.util import note_scorer_call
from evrptw_autolab.problem.v2.charging import resolve_charge
from evrptw_autolab.problem.v2.features import FEATURE_SCHEMA_VERSION
from evrptw_autolab.problem.v2.transport import (
    EPSILON,
    energy_required,
    travel_distance,
    travel_time,
)
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, VehicleTypeV2

# Same sentinel as components.interfaces.FINITE_DUE_SENTINEL. Kept local to avoid
# importing the components package from the solver (that import is cyclic).
_DUE_SENTINEL = 1.0e6


@dataclass(frozen=True, slots=True)
class StationChoice:
    """One station after the feasibility filter. ``score`` is set only when accepted."""

    station_id: str
    accepted: bool
    reason: str
    detour: float
    battery_at_station: float
    energy_slack_ratio: float
    route_time_slack_ratio: float | None
    charge_energy: float
    charge_duration: float
    charge_amount: float | None
    score: float | None
    feature_schema: str = FEATURE_SCHEMA_VERSION


def rank_station_candidates(
    spec: ProblemSpecV2,
    left_id: str,
    right_id: str,
    vehicle: VehicleTypeV2,
    *,
    battery_arrival: float,
    policy: object | None = None,
    time_at_left: float = 0.0,
    suffix_ids: list[str] | None = None,
) -> tuple[StationChoice | None, list[StationChoice]]:
    """Filter stations, then let the heuristic rank the survivors. Lower score wins.

    Equal scores break ties by shorter detour, then station id. That tie-break
    is not a replacement of a strict heuristic preference.
    """
    suffix = list(suffix_ids) if suffix_ids else [right_id]
    if not suffix or suffix[0] != right_id:
        suffix = [right_id, *suffix]
    decisions: list[StationChoice] = []
    for node in spec.nodes:
        if node.kind != "station":
            continue
        assessed = _assess(
            spec,
            left_id,
            node.id,
            vehicle,
            battery_arrival=battery_arrival,
            time_at_left=time_at_left,
            suffix=suffix,
        )
        # One station often cannot cover the whole suffix. Keep it when the next
        # hop is feasible so later repair inserts can finish the route.
        if not assessed.accepted and assessed.reason == "downstream_energy" and len(suffix) > 1:
            local = _assess(
                spec,
                left_id,
                node.id,
                vehicle,
                battery_arrival=battery_arrival,
                time_at_left=time_at_left,
                suffix=suffix[:1],
            )
            if local.accepted:
                assessed = replace(local, reason="ok_next_hop")
        decisions.append(assessed)
    survivors = [item for item in decisions if item.accepted]
    scored: list[StationChoice] = []
    scorer = getattr(policy, "station_score", None) if policy is not None else None
    for item in survivors:
        if scorer is not None:
            note_scorer_call(policy, "station_score")
            value = float(scorer(item.detour, item.battery_at_station, _rate(spec, item.station_id)))
        else:
            value = float(item.detour)
        scored.append(
            StationChoice(
                station_id=item.station_id,
                accepted=True,
                reason=item.reason,
                detour=item.detour,
                battery_at_station=item.battery_at_station,
                energy_slack_ratio=item.energy_slack_ratio,
                route_time_slack_ratio=item.route_time_slack_ratio,
                charge_energy=item.charge_energy,
                charge_duration=item.charge_duration,
                charge_amount=item.charge_amount,
                score=value,
            )
        )
    scored.sort(
        key=lambda item: (
            float(item.score if item.score is not None else 0.0),
            item.detour,
            item.station_id,
        )
    )
    rejected = [item for item in decisions if not item.accepted]
    ordered = scored + rejected
    _remember(policy, ordered)
    return (scored[0] if scored else None, ordered)


def _remember(policy: object | None, decisions: list[StationChoice]) -> None:
    if policy is None:
        return
    trace = getattr(policy, "station_trace", None)
    if isinstance(trace, list):
        trace.extend(decision_record(item) for item in decisions)


def decision_record(item: StationChoice) -> dict[str, object]:
    return {
        "station_id": item.station_id,
        "accepted": item.accepted,
        "reason": item.reason,
        "detour": item.detour,
        "battery_at_station": item.battery_at_station,
        "energy_slack_ratio": item.energy_slack_ratio,
        "route_time_slack_ratio": item.route_time_slack_ratio,
        "charge_energy": item.charge_energy,
        "charge_duration": item.charge_duration,
        "charge_amount": item.charge_amount,
        "score": item.score,
        "feature_schema": item.feature_schema,
    }


def _rate(spec: ProblemSpecV2, station_id: str) -> float:
    return float(spec.node_map[station_id].recharging_rate or 0.0)


def _assess(
    spec: ProblemSpecV2,
    left_id: str,
    station_id: str,
    vehicle: VehicleTypeV2,
    *,
    battery_arrival: float,
    time_at_left: float,
    suffix: list[str],
) -> StationChoice:
    left = spec.node_map[left_id]
    station = spec.node_map[station_id]
    right = spec.node_map[suffix[0]]
    cap = float(vehicle.battery_capacity or 0.0)
    blank = StationChoice(
        station_id=station_id,
        accepted=False,
        reason="rejected",
        detour=0.0,
        battery_at_station=0.0,
        energy_slack_ratio=0.0,
        route_time_slack_ratio=None,
        charge_energy=0.0,
        charge_duration=0.0,
        charge_amount=None,
        score=None,
    )
    try:
        to_station = energy_required(spec, left, station, vehicle)
        direct = energy_required(spec, left, right, vehicle)
        detour = travel_distance(spec, left, station) + travel_distance(spec, station, right)
    except ValueError as error:
        return _copy(blank, reason=f"incompatible_charge:{error}")
    if battery_arrival + EPSILON < to_station:
        return _copy(blank, reason="unreachable", detour=detour)
    battery_at_station = battery_arrival - to_station
    if to_station <= EPSILON and energy_required(spec, station, right, vehicle) >= direct - EPSILON:
        return _copy(blank, reason="no_progress", detour=detour, battery_at_station=battery_at_station, cap=cap)
    if spec.capabilities.multiple_charge_technologies:
        return _assess_deferred_charge(
            spec, vehicle, left_id, station_id, suffix, battery_at_station, time_at_left, detour, cap
        )
    plans = _feasible_plans(
        spec,
        vehicle,
        station_id,
        battery_at_station,
        time_at_left,
        left_id,
        suffix,
    )
    if not plans:
        reason = _failure_reason(spec, vehicle, station_id, battery_at_station, time_at_left, left_id, suffix)
        return _copy(blank, reason=reason, detour=detour, battery_at_station=battery_at_station, cap=cap)
    # Keep a feasible full charge when one exists. Partial is used only when full
    # charge misses a window, the duration limit, or the energy suffix.
    full_plans = [item for item in plans if item[2] is None]
    pool = full_plans or plans
    best = min(pool, key=lambda item: (item[1], item[0]))
    charge_energy, charge_duration, charge_amount, slack, _arrival = best
    return StationChoice(
        station_id=station_id,
        accepted=True,
        reason="ok",
        detour=detour,
        battery_at_station=battery_at_station,
        energy_slack_ratio=(battery_at_station / cap) if cap > EPSILON else 0.0,
        route_time_slack_ratio=slack,
        charge_energy=charge_energy,
        charge_duration=charge_duration,
        charge_amount=charge_amount,
        score=None,
    )


def _feasible_plans(
    spec: ProblemSpecV2,
    vehicle: VehicleTypeV2,
    station_id: str,
    battery_at_station: float,
    time_at_left: float,
    left_id: str,
    suffix: list[str],
) -> list[tuple[float, float, float | None, float | None, float]]:
    cap = float(vehicle.battery_capacity or 0.0)
    targets = [cap]
    if spec.capabilities.partial_recharge and not spec.capabilities.multiple_charge_technologies:
        needed = _energy_until_recharge(spec, vehicle, station_id, suffix)
        targets.append(min(cap, battery_at_station + needed))
    plans: list[tuple[float, float, float | None, float | None, float]] = []
    seen: set[float] = set()
    for target in targets:
        if target < battery_at_station - EPSILON or target in seen:
            continue
        seen.add(target)
        projected = _project(
            spec, vehicle, left_id, station_id, suffix, battery_at_station, time_at_left, target
        )
        if projected is None:
            continue
        energy, duration, slack, arrival, explicit = projected
        plans.append((energy, duration, explicit, slack, arrival))
    return plans


def _failure_reason(
    spec: ProblemSpecV2,
    vehicle: VehicleTypeV2,
    station_id: str,
    battery_at_station: float,
    time_at_left: float,
    left_id: str,
    suffix: list[str],
) -> str:
    cap = float(vehicle.battery_capacity or 0.0)
    reason = _project_reason(
        spec, vehicle, left_id, station_id, suffix, battery_at_station, time_at_left, cap
    )
    return reason or "cannot_leave"


def _energy_until_recharge(
    spec: ProblemSpecV2, vehicle: VehicleTypeV2, station_id: str, suffix: list[str]
) -> float:
    total = 0.0
    previous = station_id
    for node_id in suffix:
        node = spec.node_map[node_id]
        total += energy_required(spec, spec.node_map[previous], node, vehicle)
        if node.kind == "station":
            break
        previous = node_id
    return total


def _project(
    spec: ProblemSpecV2,
    vehicle: VehicleTypeV2,
    left_id: str,
    station_id: str,
    suffix: list[str],
    battery_at_station: float,
    time_at_left: float,
    target: float,
) -> tuple[float, float, float | None, float, float | None] | None:
    if _project_reason(
        spec, vehicle, left_id, station_id, suffix, battery_at_station, time_at_left, target
    ):
        return None
    energy = max(0.0, target - battery_at_station)
    station = spec.node_map[station_id]
    cap = float(vehicle.battery_capacity or 0.0)
    amount: float | None
    # A full recharge stays implicit. An explicit amount is only a partial plan.
    if target >= cap - EPSILON or energy <= EPSILON or not spec.capabilities.partial_recharge:
        amount = None
    else:
        amount = energy
    stop = RouteStopV2(station_id, event="charge", charge_amount=amount)
    decision = resolve_charge(spec, vehicle, station, stop, battery_at_station)
    clock = time_at_left + travel_time(spec, spec.node_map[left_id], station, vehicle) + decision.duration
    arrival_next = clock + travel_time(spec, station, spec.node_map[suffix[0]], vehicle)
    limit = _max_travel(spec, vehicle)
    slack = None if limit is None or limit <= EPSILON else (float(limit) - _completion_time(
        spec, vehicle, left_id, station_id, suffix, time_at_left, decision.duration
    )) / float(limit)
    explicit = amount
    return energy, decision.duration, slack, arrival_next, explicit


def _completion_time(
    spec: ProblemSpecV2,
    vehicle: VehicleTypeV2,
    left_id: str,
    station_id: str,
    suffix: list[str],
    time_at_left: float,
    charge_duration: float,
) -> float:
    clock = time_at_left + travel_time(spec, spec.node_map[left_id], spec.node_map[station_id], vehicle)
    clock += charge_duration + spec.node_map[station_id].service_time
    previous = station_id
    for node_id in suffix:
        node = spec.node_map[node_id]
        clock += travel_time(spec, spec.node_map[previous], node, vehicle)
        if node.kind in {"customer", "pickup", "delivery", "station"}:
            clock = max(clock, node.ready_time) + node.service_time
        previous = node_id
    return clock


def _project_reason(
    spec: ProblemSpecV2,
    vehicle: VehicleTypeV2,
    left_id: str,
    station_id: str,
    suffix: list[str],
    battery_at_station: float,
    time_at_left: float,
    target: float,
) -> str | None:
    cap = float(vehicle.battery_capacity or 0.0)
    if target > cap + EPSILON:
        return "cannot_leave"
    energy = max(0.0, target - battery_at_station)
    amount = None if energy <= EPSILON or not spec.capabilities.partial_recharge else energy
    station = spec.node_map[station_id]
    stop = RouteStopV2(station_id, event="charge", charge_amount=amount)
    if spec.capabilities.multiple_charge_technologies and station.charge_technologies:
        # The recharge DP owns the amount. Reject only a technology the station cannot host.
        if stop.charge_technology and stop.charge_technology not in station.charge_technologies:
            return "incompatible_charge"
    decision = resolve_charge(spec, vehicle, station, stop, max(0.0, battery_at_station))
    hard = [err for err in decision.errors if not str(err).endswith("missing_charge_decision")]
    if battery_at_station < -EPSILON:
        hard = [err for err in hard if err != "negative_battery_on_arrival"]
    if any(
        err.startswith("incompatible") or err.startswith("missing_nonlinear") or err.startswith("missing_charge")
        for err in hard
    ):
        return "incompatible_charge"
    if decision.battery_departure + EPSILON < energy_required(spec, station, spec.node_map[suffix[0]], vehicle):
        return "cannot_leave"
    battery = decision.battery_departure
    clock = time_at_left + travel_time(spec, spec.node_map[left_id], station, vehicle) + decision.duration
    clock += station.service_time
    previous = station_id
    for index, node_id in enumerate(suffix):
        node = spec.node_map[node_id]
        need = energy_required(spec, spec.node_map[previous], node, vehicle)
        clock += travel_time(spec, spec.node_map[previous], node, vehicle)
        battery -= need
        if battery < -EPSILON:
            return "cannot_leave" if index == 0 else "downstream_energy"
        if node.kind in {"customer", "pickup", "delivery"} and node.due_time < _DUE_SENTINEL:
            if clock - node.due_time > EPSILON:
                return "window"
            clock = max(clock, node.ready_time) + node.service_time
        elif node.kind == "station":
            break
        previous = node_id
    limit = _max_travel(spec, vehicle)
    if limit is not None and clock - float(limit) > EPSILON:
        return "duration"
    return None


def _max_travel(spec: ProblemSpecV2, vehicle: VehicleTypeV2) -> float | None:
    if not spec.capabilities.max_route_duration:
        return None
    raw = vehicle.metadata.get("max_travel_time", spec.metadata.get("max_travel_time"))
    if raw is None:
        return None
    return float(raw)


def _assess_deferred_charge(
    spec: ProblemSpecV2,
    vehicle: VehicleTypeV2,
    left_id: str,
    station_id: str,
    suffix: list[str],
    battery_at_station: float,
    time_at_left: float,
    detour: float,
    cap: float,
) -> StationChoice:
    """Bezzi amounts are chosen later by the recharge DP. Check reach and departure only."""
    station = spec.node_map[station_id]
    if not station.charge_technologies:
        return StationChoice(
            station_id,
            False,
            "incompatible_charge",
            detour,
            battery_at_station,
            (battery_at_station / cap) if cap > EPSILON else 0.0,
            None,
            0.0,
            0.0,
            None,
            None,
        )
    battery = cap
    clock = time_at_left + travel_time(spec, spec.node_map[left_id], station, vehicle)
    previous = station_id
    reason = "ok"
    for index, node_id in enumerate(suffix):
        node = spec.node_map[node_id]
        need = energy_required(spec, spec.node_map[previous], node, vehicle)
        clock += travel_time(spec, spec.node_map[previous], node, vehicle)
        battery -= need
        if battery < -EPSILON:
            reason = "cannot_leave" if index == 0 else "downstream_energy"
            break
        if node.kind in {"customer", "pickup", "delivery"} and node.due_time < _DUE_SENTINEL:
            if clock - node.due_time > EPSILON:
                reason = "window"
                break
        if node.kind == "station":
            break
        previous = node_id
    limit = _max_travel(spec, vehicle)
    if reason == "ok" and limit is not None and clock - float(limit) > EPSILON:
        reason = "duration"
    accepted = reason == "ok"
    return StationChoice(
        station_id=station_id,
        accepted=accepted,
        reason=reason if not accepted else "ok",
        detour=detour,
        battery_at_station=battery_at_station,
        energy_slack_ratio=(battery_at_station / cap) if cap > EPSILON else 0.0,
        route_time_slack_ratio=None if limit is None or limit <= EPSILON else (float(limit) - clock) / float(limit),
        charge_energy=0.0,
        charge_duration=0.0,
        charge_amount=None,
        score=None,
    )


def _copy(
    blank: StationChoice,
    *,
    reason: str,
    detour: float = 0.0,
    battery_at_station: float = 0.0,
    cap: float = 0.0,
) -> StationChoice:
    ratio = (battery_at_station / cap) if cap > EPSILON else 0.0
    return StationChoice(
        station_id=blank.station_id,
        accepted=False,
        reason=reason,
        detour=detour,
        battery_at_station=battery_at_station,
        energy_slack_ratio=ratio,
        route_time_slack_ratio=None,
        charge_energy=0.0,
        charge_duration=0.0,
        charge_amount=None,
        score=None,
    )
