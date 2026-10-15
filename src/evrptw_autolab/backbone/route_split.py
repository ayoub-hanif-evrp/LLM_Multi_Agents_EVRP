"""Split overloaded routes when charging repair cannot restore feasibility."""
from __future__ import annotations

from evrptw_autolab.backbone.charge_completion import complete_solution_charges
from evrptw_autolab.backbone.energy_repair import repair_energy
from evrptw_autolab.backbone.util import (
    clone_solution,
    default_vehicle_id,
    empty_route,
    evaluate,
    make_customer_stop,
)
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2

_SPLIT_FAMILIES = frozenset({"BATTERY", "CHARGE_POLICY", "WINDOW", "DURATION"})


def _units_on_route(spec: ProblemSpecV2, route) -> list[tuple[str, ...]]:
    ids = {s.node_id for s in route}
    if spec.capabilities.pickup_delivery and spec.requests:
        units = []
        for req in spec.requests:
            if req.pickup_id in ids and req.delivery_id in ids:
                units.append((req.pickup_id, req.delivery_id))
        return units
    return [(s.node_id,) for s in route if spec.node_map[s.node_id].kind == "customer"]


def _strip_request_nodes(route, node_ids: set[str]):
    from evrptw_autolab.problem.v2.types import RouteStopV2

    body = [s for s in route if s.event != "depot" and s.node_id not in node_ids]
    if not body:
        return None
    depot = route[0].node_id
    vid = route[0].vehicle_type_id
    return [
        RouteStopV2(depot, vehicle_type_id=vid, event="depot"),
        *body,
        RouteStopV2(depot, vehicle_type_id=vid, event="depot"),
    ]


def _fleet_room(spec: ProblemSpecV2, solution: SolutionV2, type_id: str) -> bool:
    """True if opening one more route of type_id stays within fleet availability."""
    limit = spec.fleet_availability.get(type_id)
    if limit is None or limit >= 10**8:
        return True
    used = sum(1 for a in solution.vehicle_assignments if a == type_id)
    # Count routes resolved via stop annotations when assignments are short.
    if len(solution.vehicle_assignments) < len(solution.routes):
        used = len(solution.routes)
    return used < int(limit)


def split_infeasible_routes(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    max_splits: int = 24,
    policy: object | None = None,
) -> SolutionV2:
    """Peel request units from routes that remain energy/time infeasible after repair."""
    current = clone_solution(solution)
    current = repair_energy(spec, current, policy=policy)
    current = complete_solution_charges(spec, current)
    splits = 0
    while splits < max_splits:
        report = evaluate(spec, current)
        if report.feasible:
            break
        if not any(v.family in _SPLIT_FAMILIES for v in report.violations):
            break
        progress = False
        for r_idx, route in enumerate(list(current.routes)):
            units = _units_on_route(spec, route)
            if len(units) <= 1:
                continue
            # Peel the last unit onto a dedicated route.
            unit = units[-1]
            trial = clone_solution(current)
            stripped = _strip_request_nodes(trial.routes[r_idx], set(unit))
            assign = (
                trial.vehicle_assignments[r_idx]
                if r_idx < len(trial.vehicle_assignments)
                else default_vehicle_id(spec)
            )
            if stripped is None:
                # Remove empty route atomically with its assignment.
                del trial.routes[r_idx]
                if r_idx < len(trial.vehicle_assignments):
                    del trial.vehicle_assignments[r_idx]
            else:
                trial.routes[r_idx] = stripped
                if not _fleet_room(spec, trial, assign):
                    continue
            new_route = empty_route(spec, assign)
            for nid in unit:
                new_route.insert(-1, make_customer_stop(nid, spec))
            trial.routes.append(new_route)
            trial.vehicle_assignments.append(assign)
            trial = repair_energy(spec, trial, policy=policy)
            trial = complete_solution_charges(spec, trial)
            trial_report = evaluate(spec, trial)
            if any(v.family == "FLEET" for v in trial_report.violations):
                continue
            if _accept_split(report, trial_report):
                current = trial
                splits += 1
                progress = True
                break
        if not progress:
            # Fallback: peel first unit if last peel failed.
            progressed = False
            for r_idx, route in enumerate(list(current.routes)):
                units = _units_on_route(spec, route)
                if len(units) <= 1:
                    continue
                unit = units[0]
                trial = clone_solution(current)
                stripped = _strip_request_nodes(trial.routes[r_idx], set(unit))
                assign = (
                    trial.vehicle_assignments[r_idx]
                    if r_idx < len(trial.vehicle_assignments)
                    else default_vehicle_id(spec)
                )
                if stripped is None:
                    del trial.routes[r_idx]
                    if r_idx < len(trial.vehicle_assignments):
                        del trial.vehicle_assignments[r_idx]
                else:
                    trial.routes[r_idx] = stripped
                    if not _fleet_room(spec, trial, assign):
                        continue
                new_route = empty_route(spec, assign)
                for nid in unit:
                    new_route.insert(-1, make_customer_stop(nid, spec))
                trial.routes.append(new_route)
                trial.vehicle_assignments.append(assign)
                trial = repair_energy(spec, trial, policy=policy)
                trial = complete_solution_charges(spec, trial)
                trial_report = evaluate(spec, trial)
                if any(v.family == "FLEET" for v in trial_report.violations):
                    continue
                if _accept_split(report, trial_report):
                    current = trial
                    splits += 1
                    progressed = True
                    break
            if not progressed:
                break
    current.metadata["route_splits"] = splits
    return current


def _accept_split(old, new) -> bool:
    if new.feasible:
        return True
    old_hard = sum(1 for v in old.violations if v.family in _SPLIT_FAMILIES)
    new_hard = sum(1 for v in new.violations if v.family in _SPLIT_FAMILIES)
    if new_hard < old_hard:
        return True
    if len(new.unserved) < len(old.unserved):
        return True
    old_mag = sum(float(v.magnitude or 0.0) for v in old.violations if v.family in _SPLIT_FAMILIES)
    new_mag = sum(float(v.magnitude or 0.0) for v in new.violations if v.family in _SPLIT_FAMILIES)
    return new_hard <= old_hard and new_mag + 1e-6 < old_mag
