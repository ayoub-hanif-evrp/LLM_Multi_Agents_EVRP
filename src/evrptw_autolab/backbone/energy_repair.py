"""Charging-station insertion repair for energy-infeasible routes."""
from __future__ import annotations

import time

from evrptw_autolab.backbone.charge_completion import complete_solution_charges
from evrptw_autolab.backbone.station_filter import rank_station_candidates
from evrptw_autolab.backbone.util import (
    clone_solution,
    evaluate,
    vehicle_for_route,
)
from evrptw_autolab.problem.v2.route_simulator import simulate_route
from evrptw_autolab.problem.v2.transport import EPSILON, energy_required
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2


def _stations(spec: ProblemSpecV2) -> list[str]:
    return [n.id for n in spec.nodes if n.kind == "station"]


def _best_station_between(
    spec: ProblemSpecV2,
    left_id: str,
    right_id: str,
    vehicle,
    *,
    battery_arrival: float = 0.0,
    policy: object | None = None,
    time_at_left: float = 0.0,
    suffix_ids: list[str] | None = None,
) -> str | None:
    """Rank stations that survive trusted resource checks. The score is not a checker."""
    choice, _decisions = rank_station_candidates(
        spec,
        left_id,
        right_id,
        vehicle,
        battery_arrival=battery_arrival,
        policy=policy,
        time_at_left=time_at_left,
        suffix_ids=suffix_ids,
    )
    return None if choice is None else choice.station_id


def repair_energy(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    max_inserts: int = 40,
    policy: object | None = None,
    deadline: float | None = None,
) -> SolutionV2:
    """Insert stations until battery-feasible or inserts exhausted.

    For multi-technology Bezzi instances, charge amounts are completed by the
    optimizer-side DP after each structural change. Non-Bezzi families still use
    implicit full recharge when charge_amount is unset.
    """
    if not spec.capabilities.battery:
        return solution

    current = complete_solution_charges(spec, clone_solution(solution))
    inserts = 0
    while inserts < max_inserts:
        if deadline is not None and time.monotonic() > deadline:
            break
        current = complete_solution_charges(spec, current)
        report = evaluate(spec, current)
        hard_energy = any(v.family in {"BATTERY", "CHARGE_POLICY"} for v in report.violations)
        if report.feasible or not hard_energy:
            break
        if not _stations(spec) and not spec.capabilities.multiple_charge_technologies:
            break
        progress = False
        for r_idx, route in enumerate(current.routes):
            try:
                vehicle = vehicle_for_route(spec, current, r_idx)
            except ValueError:
                continue
            if vehicle.is_conventional and not vehicle.is_electric and not vehicle.is_hybrid:
                continue
            try:
                traj, _ = simulate_route(spec, route, vehicle)
            except (KeyError, ValueError):
                continue
            candidates = _find_station_insertions(spec, route, vehicle, traj, policy=policy)
            for insert_pos, station_id, charge_amount in candidates:
                if deadline is not None and time.monotonic() > deadline:
                    return current
                if insert_pos > 0 and route[insert_pos - 1].node_id == station_id:
                    continue
                trial = clone_solution(current)
                trial.routes[r_idx].insert(
                    insert_pos,
                    RouteStopV2(
                        station_id,
                        vehicle_type_id=vehicle.type_id,
                        event="charge",
                        charge_amount=charge_amount,
                    ),
                )
                if spec.capabilities.multiple_charge_technologies:
                    trial.routes[r_idx] = [
                        RouteStopV2(
                            node_id=s.node_id,
                            vehicle_type_id=s.vehicle_type_id,
                            event=s.event,
                            charge_amount=None,
                            charge_technology=None,
                            target_soc=None,
                        )
                        for s in trial.routes[r_idx]
                    ]
                trial = complete_solution_charges(spec, trial)
                trial_report = evaluate(spec, trial)
                old_batt = sum(
                    1 for v in report.violations if v.family in {"BATTERY", "CHARGE_POLICY"}
                )
                new_batt = sum(
                    1 for v in trial_report.violations if v.family in {"BATTERY", "CHARGE_POLICY"}
                )
                old_dur = sum(1 for v in report.violations if v.family == "DURATION")
                new_dur = sum(1 for v in trial_report.violations if v.family == "DURATION")
                old_win = sum(1 for v in report.violations if v.family == "WINDOW")
                new_win = sum(1 for v in trial_report.violations if v.family == "WINDOW")
                old_mag = sum(
                    float(v.magnitude or 0.0)
                    for v in report.violations
                    if v.family in {"BATTERY", "CHARGE_POLICY"}
                )
                new_mag = sum(
                    float(v.magnitude or 0.0)
                    for v in trial_report.violations
                    if v.family in {"BATTERY", "CHARGE_POLICY"}
                )
                # Route-local battery magnitude (ignore other routes / VISIT noise).
                old_route_mag = sum(
                    float(v.magnitude or 0.0)
                    for v in report.violations
                    if v.family in {"BATTERY", "CHARGE_POLICY"} and v.route_index == r_idx
                )
                new_route_mag = sum(
                    float(v.magnitude or 0.0)
                    for v in trial_report.violations
                    if v.family in {"BATTERY", "CHARGE_POLICY"} and v.route_index == r_idx
                )
                accept = trial_report.feasible or new_batt < old_batt or is_better_coverage(
                    trial_report, report
                )
                if not accept and new_batt <= old_batt and new_mag + EPSILON < old_mag:
                    accept = True
                if not accept and new_route_mag + EPSILON < old_route_mag:
                    accept = True
                if spec.capabilities.multiple_charge_technologies:
                    # Bezzi DP often needs several coordinated station inserts plus a
                    # depot recharge; accept structural station progress even when the
                    # violation count temporarily rises.
                    added_station = len(trial.routes[r_idx]) > len(route)
                    if added_station and len(trial_report.unserved) <= len(report.unserved):
                        accept = True
                if new_win > old_win and not trial_report.feasible:
                    accept = False
                if new_dur > old_dur and new_batt >= old_batt and not trial_report.feasible:
                    accept = False
                if accept:
                    current = trial
                    inserts += 1
                    progress = True
                    break
            if progress:
                break
        if not progress:
            break
    current = complete_solution_charges(spec, current)
    current.metadata["energy_repair_inserts"] = inserts
    return current


def _soc_at_index(spec: ProblemSpecV2, route: list[RouteStopV2], vehicle, index: int) -> float | None:
    """Battery SoC on arrival at route[index], assuming full recharge at every station."""
    cap = float(vehicle.battery_capacity or 0.0)
    soc = cap
    for k in range(1, index + 1):
        a = spec.node_map[route[k - 1].node_id]
        b = spec.node_map[route[k].node_id]
        if a.kind == "station":
            soc = cap
        try:
            need = energy_required(spec, a, b, vehicle)
        except ValueError:
            return None
        if soc + EPSILON < need:
            return None
        soc -= need
    return soc


def _find_station_insertions(
    spec: ProblemSpecV2,
    route: list[RouteStopV2],
    vehicle,
    traj,
    *,
    policy: object | None = None,
) -> list[tuple[int, str, float | None]]:
    """Ranked station insertion candidates for an energy-infeasible route."""
    cap = float(vehicle.battery_capacity or 0.0)
    if cap <= EPSILON:
        return []

    def _candidate(
        left_id: str, right_id: str, battery_arrival: float, insert_pos: int
    ) -> tuple[int, str, float | None] | None:
        suffix = [stop.node_id for stop in route[insert_pos:]]
        clock = 0.0
        if traj is not None and insert_pos > 0 and insert_pos - 1 < len(traj):
            clock = float(traj[insert_pos - 1].departure_time)
        choice, _decisions = rank_station_candidates(
            spec,
            left_id,
            right_id,
            vehicle,
            battery_arrival=max(0.0, battery_arrival),
            policy=policy,
            time_at_left=clock,
            suffix_ids=suffix or [right_id],
        )
        if choice is None:
            return None
        station_id = choice.station_id
        if insert_pos > 0 and route[insert_pos - 1].node_id == station_id:
            return None
        if insert_pos < len(route) and route[insert_pos].node_id == station_id:
            return None
        return insert_pos, station_id, choice.charge_amount

    battery = cap
    fail_at: int | None = None
    fail_battery = 0.0
    for i in range(1, len(route)):
        left_id = route[i - 1].node_id
        right_id = route[i].node_id
        left = spec.node_map[left_id]
        if left.kind == "station":
            battery = cap
        try:
            need = energy_required(spec, left, spec.node_map[right_id], vehicle)
        except ValueError:
            return []
        if battery + EPSILON >= need:
            battery -= need
            continue
        fail_at = i
        fail_battery = battery
        break

    if fail_at is None:
        for i, state in enumerate(traj):
            if i == 0:
                continue
            if state.battery_arrival < -EPSILON:
                fail_at = i
                fail_battery = float(traj[i - 1].battery_departure)
                break
        if fail_at is None:
            return []

    ordered: list[tuple[int, str, float | None]] = []
    seen: set[tuple[int, str]] = set()

    def _push(hit: tuple[int, str, float | None] | None) -> None:
        if hit is None:
            return
        key = (hit[0], hit[1])
        if key in seen:
            return
        seen.add(key)
        ordered.append(hit)

    # 1) Failing hop.
    _push(
        _candidate(
            route[fail_at - 1].node_id,
            route[fail_at].node_id,
            fail_battery,
            fail_at,
        )
    )
    # 2) Near-failure hops (immediately upstream), then depot-side.
    near = list(range(fail_at - 1, 0, -1))
    early = [0] if fail_at > 0 else []
    for j in near + early:
        left_id = route[j].node_id
        right_id = route[j + 1].node_id
        if j == 0:
            soc = float(cap)
        else:
            soc_at = _soc_at_index(spec, route, vehicle, j)
            if soc_at is None:
                continue
            soc = float(cap) if spec.node_map[left_id].kind == "station" else float(soc_at)
        _push(_candidate(left_id, right_id, soc, j + 1))
    return ordered


def is_better_coverage(a, b) -> bool:
    return len(a.unserved) < len(b.unserved) or (
        len(a.unserved) == len(b.unserved) and len(a.violations) < len(b.violations)
    )


def remove_redundant_stations(spec: ProblemSpecV2, solution: SolutionV2) -> SolutionV2:
    """Drop station visits whose removal keeps feasibility."""
    current = clone_solution(solution)
    changed = True
    while changed:
        changed = False
        for r_idx, route in enumerate(current.routes):
            for i in range(len(route) - 2, 0, -1):
                if spec.node_map[route[i].node_id].kind != "station":
                    continue
                trial = clone_solution(current)
                del trial.routes[r_idx][i]
                if evaluate(spec, trial).feasible:
                    current = trial
                    changed = True
                    break
            if changed:
                break
    return current
