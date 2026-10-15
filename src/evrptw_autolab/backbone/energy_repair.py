"""Charging-station insertion repair for energy-infeasible routes."""
from __future__ import annotations

from evrptw_autolab.backbone.charge_completion import complete_solution_charges
from evrptw_autolab.backbone.util import (
    clone_solution,
    evaluate,
    vehicle_for_route,
)
from evrptw_autolab.problem.v2.route_simulator import simulate_route
from evrptw_autolab.problem.v2.transport import EPSILON, energy_required, travel_distance
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
) -> str | None:
    """Pick a reachable station; never choose one the vehicle cannot reach from left."""
    stations = _stations(spec)
    if not stations:
        return None
    left = spec.node_map[left_id]
    right = spec.node_map[right_id]
    scorer = getattr(policy, "station_score", None) if policy is not None else None
    best = None
    best_cost = float("inf")
    for sid in stations:
        station = spec.node_map[sid]
        try:
            to_station = energy_required(spec, left, station, vehicle)
            from_station = energy_required(spec, station, right, vehicle)
        except ValueError:
            continue
        if battery_arrival + EPSILON < to_station:
            continue
        # Skip depot-colocated / zero-progress stations (Bezzi station 5 sits on the depot).
        if to_station <= EPSILON and from_station >= energy_required(spec, left, right, vehicle) - EPSILON:
            continue
        detour = travel_distance(spec, left, station) + travel_distance(spec, station, right)
        rate = float(station.recharging_rate or 0.0)
        cost = float(scorer(detour, battery_arrival, rate)) if scorer is not None else float(detour)
        if cost < best_cost:
            best_cost = cost
            best = sid
    return best


def repair_energy(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    max_inserts: int = 40,
    policy: object | None = None,
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
            insertion = _find_station_insertion(spec, route, vehicle, traj, policy=policy)
            if insertion is None:
                continue
            insert_pos, station_id = insertion
            if insert_pos > 0 and route[insert_pos - 1].node_id == station_id:
                continue
            # Avoid only immediate consecutive duplicates; station revisits are allowed.
            trial = clone_solution(current)
            trial.routes[r_idx].insert(
                insert_pos,
                RouteStopV2(station_id, vehicle_type_id=vehicle.type_id, event="charge"),
            )
            # Clear prior charge annotations so DP recomputes for the new sequence.
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
            old_batt = sum(1 for v in report.violations if v.family in {"BATTERY", "CHARGE_POLICY"})
            new_batt = sum(
                1 for v in trial_report.violations if v.family in {"BATTERY", "CHARGE_POLICY"}
            )
            old_dur = sum(1 for v in report.violations if v.family == "DURATION")
            new_dur = sum(1 for v in trial_report.violations if v.family == "DURATION")
            accept = trial_report.feasible or new_batt < old_batt or is_better_coverage(
                trial_report, report
            )
            if spec.capabilities.multiple_charge_technologies and len(trial_report.unserved) <= len(
                report.unserved
            ):
                # Bezzi may need several inserts before DP succeeds.
                accept = accept or len(trial.routes[r_idx]) > len(route)
            if new_dur > old_dur and new_batt >= old_batt and not trial_report.feasible:
                accept = False
            if accept:
                current = trial
                inserts += 1
                progress = True
                break
        if not progress:
            break
    current = complete_solution_charges(spec, current)
    current.metadata["energy_repair_inserts"] = inserts
    return current


def _find_station_insertion(
    spec: ProblemSpecV2,
    route: list[RouteStopV2],
    vehicle,
    traj,
    *,
    policy: object | None = None,
) -> tuple[int, str] | None:
    """Return (insert_pos, station_id) for the first energy-critical hop that is repairable."""
    cap = float(vehicle.battery_capacity or 0.0)
    if cap <= EPSILON:
        return None

    # Walk as if the vehicle left the last charge opportunity with a full battery.
    battery = cap
    for i in range(1, len(route)):
        left_id = route[i - 1].node_id
        right_id = route[i].node_id
        left = spec.node_map[left_id]
        right = spec.node_map[right_id]
        if left.kind == "station":
            battery = cap
        try:
            need = energy_required(spec, left, right, vehicle)
        except ValueError:
            return None
        if battery + EPSILON >= need:
            battery -= need
            continue
        # Cannot reach next node: insert a station before this hop if reachable from left.
        station_id = _best_station_between(
            spec, left_id, right_id, vehicle, battery_arrival=max(0.0, battery), policy=policy
        )
        if station_id is not None:
            return i, station_id
        # If already at a station or no reachable station from here, try earlier positions
        # where a station was still reachable and the remaining suffix is heavy.
        for j in range(i - 1, 0, -1):
            prev_id = route[j].node_id
            nxt_id = route[j + 1].node_id if j + 1 < len(route) else right_id
            # Reconstruct SoC at j assuming full start and full recharge at stations.
            soc = cap
            ok = True
            for k in range(1, j + 1):
                a = spec.node_map[route[k - 1].node_id]
                b = spec.node_map[route[k].node_id]
                if a.kind == "station":
                    soc = cap
                try:
                    e = energy_required(spec, a, b, vehicle)
                except ValueError:
                    ok = False
                    break
                if soc + EPSILON < e:
                    ok = False
                    break
                soc -= e
            if not ok:
                continue
            sid = _best_station_between(
                spec, prev_id, nxt_id, vehicle, battery_arrival=max(0.0, soc), policy=policy
            )
            if sid is not None and route[j].node_id != sid:
                return j + 1, sid
        return None

    # Trajectory already negative under explicit simulation (non-Bezzi).
    for i, state in enumerate(traj):
        if i == 0:
            continue
        if state.battery_arrival < -EPSILON:
            left_id = route[i - 1].node_id
            right_id = route[i].node_id
            batt_left = traj[i - 1].battery_departure
            station_id = _best_station_between(
                spec, left_id, right_id, vehicle, battery_arrival=max(0.0, batt_left), policy=policy
            )
            if station_id is not None:
                return i, station_id
            return None
    return None


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
