"""Partial-charge optimization for nonlinear (Montoya-style) routes."""
from __future__ import annotations

from evrptw_autolab.backbone.util import clone_solution, vehicle_for_route
from evrptw_autolab.problem.v2.charging import nonlinear_charge_duration
from evrptw_autolab.problem.v2.route_simulator import simulate_route
from evrptw_autolab.problem.v2.transport import EPSILON, energy_required
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2, VehicleTypeV2


def _suffix_energy(spec: ProblemSpecV2, route: list[RouteStopV2], start: int, vehicle: VehicleTypeV2) -> float:
    total = 0.0
    for i in range(start, len(route) - 1):
        total += energy_required(
            spec,
            spec.node_map[route[i].node_id],
            spec.node_map[route[i + 1].node_id],
            vehicle,
        )
        # If another station follows, only need energy to that station.
        if i + 1 < len(route) and spec.node_map[route[i + 1].node_id].kind == "station":
            break
    return total


def optimize_route_partial_charges(
    spec: ProblemSpecV2,
    route: list[RouteStopV2],
    vehicle: VehicleTypeV2,
) -> list[RouteStopV2]:
    """Set station target_soc to the minimum energy needed for the next segment."""
    if not spec.capabilities.nonlinear_charging:
        return route
    cap = float(vehicle.battery_capacity or 0.0)
    if cap <= EPSILON:
        return route
    funcs = spec.metadata.get("charging_functions") or vehicle.metadata.get("charging_functions") or {}
    battery = cap
    out: list[RouteStopV2] = []
    for index, stop in enumerate(route):
        node = spec.node_map[stop.node_id]
        if index:
            need = energy_required(
                spec,
                spec.node_map[route[index - 1].node_id],
                node,
                vehicle,
            )
            battery -= need
        if node.kind == "station":
            # Skip consecutive duplicate station visits (zero progress).
            if out and out[-1].node_id == stop.node_id and out[-1].event == "charge":
                continue
            # Arrive with battery; charge just enough for the suffix until next station/depot.
            suffix = _suffix_energy(spec, route, index, vehicle)
            # If the immediate next stop is another station, charge for the hop after that chain.
            nxt = index + 1
            while nxt < len(route) and spec.node_map[route[nxt].node_id].kind == "station":
                nxt += 1
            if nxt < len(route) and suffix <= EPSILON:
                suffix = _suffix_energy(spec, route, nxt - 1, vehicle)
            target = min(cap, max(battery, suffix))
            # If the published suffix exceeds capacity, charge fully; another station is required later.
            if suffix > cap + EPSILON:
                target = cap
            else:
                target = min(cap, max(target, battery) + 1e-6)
            tech = stop.charge_technology or (node.charge_technologies[0] if node.charge_technologies else None)
            if tech and tech in funcs:
                hi = float(funcs[tech][-1]["battery_level"])
                target = min(target, hi, cap)
            # Never leave a station without charging when the next non-station hop needs more energy.
            if target + EPSILON < battery:
                target = battery
            out.append(
                RouteStopV2(
                    node_id=stop.node_id,
                    vehicle_type_id=stop.vehicle_type_id,
                    event="charge",
                    target_soc=float(target),
                    charge_technology=tech,
                )
            )
            battery = float(target)
        else:
            out.append(stop)
    return _refine_partial_targets(spec, out, vehicle)


def _route_duration_ok(
    spec: ProblemSpecV2, route: list[RouteStopV2], vehicle: VehicleTypeV2
) -> tuple[bool, float]:
    traj, errors = simulate_route(spec, route, vehicle)
    if errors or not traj:
        return False, float("inf")
    ok = all(s.battery_arrival >= -EPSILON and s.battery_departure >= -EPSILON for s in traj)
    end = traj[-1].departure_time
    if ok and spec.capabilities.max_route_duration:
        limit = vehicle.metadata.get("max_travel_time", spec.metadata.get("max_travel_time"))
        if limit is not None and end > float(limit) + EPSILON:
            ok = False
    return ok, end


def _refine_partial_targets(
    spec: ProblemSpecV2,
    route: list[RouteStopV2],
    vehicle: VehicleTypeV2,
) -> list[RouteStopV2]:
    """Try a few higher SoC targets; keep only if route duration improves."""
    cap = float(vehicle.battery_capacity or 0.0)
    funcs = spec.metadata.get("charging_functions") or vehicle.metadata.get("charging_functions") or {}
    best = route
    best_ok, best_dur = _route_duration_ok(spec, route, vehicle)
    station_idxs = [i for i, s in enumerate(route) if spec.node_map[s.node_id].kind == "station"]
    for s_idx in station_idxs:
        stop = best[s_idx]
        base = float(stop.target_soc or 0.0)
        tech = stop.charge_technology
        hi = cap
        if tech and tech in funcs:
            hi = min(hi, float(funcs[tech][-1]["battery_level"]))
        for cand in (base, min(hi, base + 0.1 * cap), min(hi, 0.5 * (base + hi)), hi):
            trial = list(best)
            trial[s_idx] = RouteStopV2(
                node_id=stop.node_id,
                vehicle_type_id=stop.vehicle_type_id,
                event="charge",
                target_soc=float(cand),
                charge_technology=tech,
            )
            ok, dur = _route_duration_ok(spec, trial, vehicle)
            if (ok and not best_ok) or (ok == best_ok and dur + 1e-9 < best_dur):
                best = trial
                best_ok, best_dur = ok, dur
                stop = best[s_idx]
    return best


def optimize_solution_partial_charges(spec: ProblemSpecV2, solution: SolutionV2) -> SolutionV2:
    if not spec.capabilities.nonlinear_charging:
        return solution
    out = clone_solution(solution)
    for idx, route in enumerate(out.routes):
        try:
            vehicle = vehicle_for_route(spec, out, idx)
        except ValueError:
            continue
        out.routes[idx] = optimize_route_partial_charges(spec, route, vehicle)
    out.metadata["partial_charge_opt"] = True
    return out


def estimate_charge_time(
    spec: ProblemSpecV2,
    vehicle: VehicleTypeV2,
    tech: str | None,
    battery_arrival: float,
    battery_target: float,
) -> float:
    funcs = spec.metadata.get("charging_functions") or vehicle.metadata.get("charging_functions") or {}
    if tech is None or tech not in funcs:
        return max(0.0, battery_target - battery_arrival)  # fallback linear unit rate
    return nonlinear_charge_duration(list(funcs[tech]), battery_arrival, battery_target)
