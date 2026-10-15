"""Charging-station insertion repair for energy-infeasible routes."""
from __future__ import annotations

from evrptw_autolab.backbone.util import (
    clone_solution,
    default_vehicle_id,
    evaluate,
    vehicle_for_route,
)
from evrptw_autolab.problem.v2.route_simulator import simulate_route
from evrptw_autolab.problem.v2.transport import EPSILON, energy_required, travel_distance
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2


def _stations(spec: ProblemSpecV2) -> list[str]:
    return [n.id for n in spec.nodes if n.kind == "station"]


def _best_station_between(spec: ProblemSpecV2, left_id: str, right_id: str) -> str | None:
    stations = _stations(spec)
    if not stations:
        return None
    left = spec.node_map[left_id]
    right = spec.node_map[right_id]
    best = None
    best_cost = float("inf")
    for sid in stations:
        station = spec.node_map[sid]
        cost = travel_distance(spec, left, station) + travel_distance(spec, station, right)
        if cost < best_cost:
            best_cost = cost
            best = sid
    return best


def repair_energy(spec: ProblemSpecV2, solution: SolutionV2, *, max_inserts: int = 40) -> SolutionV2:
    """Insert stations until battery-feasible or inserts exhausted.

    Uses full-recharge station stops (charge_amount unset → charge to full).
    """
    if not spec.capabilities.battery:
        return solution
    if not _stations(spec):
        return solution

    current = clone_solution(solution)
    inserts = 0
    while inserts < max_inserts:
        report = evaluate(spec, current)
        if report.feasible or not any(v.family == "BATTERY" for v in report.violations):
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
            # Find first stop with negative battery arrival (after travel into it).
            fail_at = None
            for i, state in enumerate(traj):
                if i == 0:
                    continue
                if state.battery_arrival < -EPSILON:
                    fail_at = i
                    break
            if fail_at is None:
                continue
            # Insert station just before the failing node.
            left_id = route[fail_at - 1].node_id
            right_id = route[fail_at].node_id
            # Avoid inserting between identical consecutive stations repeatedly.
            if spec.node_map[left_id].kind == "station":
                # Try one node earlier if possible.
                if fail_at - 1 <= 0:
                    continue
                left_id = route[fail_at - 2].node_id
                insert_pos = fail_at - 1
            else:
                insert_pos = fail_at
            station_id = _best_station_between(spec, left_id, right_id)
            if station_id is None:
                continue
            # Skip if station already immediately before.
            if insert_pos > 0 and route[insert_pos - 1].node_id == station_id:
                # Try a different station: farthest energy-saving among alternatives.
                alts = [s for s in _stations(spec) if s != station_id]
                station_id = None
                best = float("inf")
                for sid in alts:
                    cost = travel_distance(
                        spec, spec.node_map[left_id], spec.node_map[sid]
                    ) + travel_distance(spec, spec.node_map[sid], spec.node_map[right_id])
                    # Prefer stations reachable with remaining battery from left.
                    if traj[insert_pos - 1].battery_departure + EPSILON >= energy_required(
                        spec, spec.node_map[left_id], spec.node_map[sid], vehicle
                    ):
                        if cost < best:
                            best = cost
                            station_id = sid
                if station_id is None:
                    continue
            trial = clone_solution(current)
            trial.routes[r_idx].insert(
                insert_pos,
                RouteStopV2(station_id, vehicle_type_id=default_vehicle_id(spec), event="charge"),
            )
            trial_report = evaluate(spec, trial)
            # Keep if battery violations do not increase.
            old_batt = sum(1 for v in report.violations if v.family == "BATTERY")
            new_batt = sum(1 for v in trial_report.violations if v.family == "BATTERY")
            if new_batt < old_batt or trial_report.feasible:
                current = trial
                inserts += 1
                progress = True
                break
        if not progress:
            break
    current.metadata["energy_repair_inserts"] = inserts
    return current


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
