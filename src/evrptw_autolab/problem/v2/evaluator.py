"""Independent variant-aware feasibility oracle. Never calls an LLM."""
from __future__ import annotations

import time
from collections import Counter

from evrptw_autolab.problem.v2.report import EvaluationReportV2, StopStateV2
from evrptw_autolab.problem.v2.route_simulator import simulate_route
from evrptw_autolab.problem.v2.transport import EPSILON
from evrptw_autolab.problem.v2.types import (
    ProblemSpecV2,
    RouteStopV2,
    SolutionV2,
    VehicleTypeV2,
)


def _vehicle_for_route(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    route_index: int,
    route: list[RouteStopV2],
) -> VehicleTypeV2:
    type_id = None
    if route_index < len(solution.vehicle_assignments) and solution.vehicle_assignments[route_index]:
        type_id = solution.vehicle_assignments[route_index]
    elif route and route[0].vehicle_type_id:
        type_id = route[0].vehicle_type_id
    elif len(spec.vehicle_types) == 1:
        type_id = spec.vehicle_types[0].type_id
    if type_id is None:
        raise ValueError(f"route {route_index}: missing vehicle type assignment")
    for vehicle in spec.vehicle_types:
        if vehicle.type_id == type_id:
            return vehicle
    raise ValueError(f"route {route_index}: unknown vehicle type {type_id!r}")


def _required_visit_ids(spec: ProblemSpecV2) -> list[str]:
    if spec.capabilities.pickup_delivery and spec.requests:
        ids: list[str] = []
        for req in spec.requests:
            ids.append(req.pickup_id)
            ids.append(req.delivery_id)
        return ids
    return [n.id for n in spec.nodes if n.kind == "customer"]


def _check_depot(
    spec: ProblemSpecV2,
    route: list[RouteStopV2],
    route_index: int,
    report: EvaluationReportV2,
    vehicle: VehicleTypeV2 | None = None,
) -> None:
    origin = spec.depot_ids[0]
    destination = spec.depot_ids[0]
    if vehicle is not None:
        origin = str(vehicle.metadata.get("departure_node") or origin)
        destination = str(vehicle.metadata.get("arrival_node") or destination)
    depot = origin
    if not route or route[0].node_id != origin or route[-1].node_id != destination:
        report.add(
            "DEPOT",
            node_id=route[0].node_id if route else "",
            route_index=route_index,
            detail="route must start and end at depot",
        )
        return
    for stop in route[1:-1]:
        if stop.node_id == depot:
            report.add(
                "DEPOT",
                node_id=depot,
                route_index=route_index,
                detail="internal depot visit not allowed",
            )
            return


def _check_pd_precedence(
    spec: ProblemSpecV2,
    route: list[RouteStopV2],
    route_index: int,
    report: EvaluationReportV2,
) -> None:
    if not spec.capabilities.pickup_delivery:
        return
    positions = {stop.node_id: i for i, stop in enumerate(route)}
    for req in spec.requests:
        if req.pickup_id in positions and req.delivery_id in positions:
            if positions[req.pickup_id] >= positions[req.delivery_id]:
                report.add(
                    "PRECEDENCE",
                    node_id=req.delivery_id,
                    route_index=route_index,
                    detail=f"delivery before pickup for {req.request_id}",
                )
        elif req.pickup_id in positions or req.delivery_id in positions:
            # Split across vehicles when same_vehicle required.
            if req.same_vehicle:
                report.add(
                    "PAIRING",
                    node_id=req.pickup_id if req.pickup_id in positions else req.delivery_id,
                    route_index=route_index,
                    detail=f"split request {req.request_id} across vehicles",
                )


def _objective(
    spec: ProblemSpecV2,
    report: EvaluationReportV2,
    trajectories: list[list[StopStateV2]],
    assignments: list[str],
) -> None:
    """Variant objectives as lexicographic tuples (all minimized)."""
    distance = report.total_distance
    vehicles = float(report.vehicles)
    duration = report.total_duration
    if spec.family == "schneider":
        report.objective_key = (vehicles, distance)
        report.objective_components = {"vehicles": vehicles, "distance": distance}
    elif spec.family == "montoya":
        report.objective_key = (duration,)
        report.objective_components = {"total_duration": duration}
    elif spec.family == "goeke":
        # Goeke (EJOR 2019) PDPTW-EV / VRP-REP: minimize fleet size then travel distance.
        report.objective_key = (vehicles, distance)
        report.objective_components = {"vehicles": vehicles, "distance": distance}
    elif spec.family == "bezzi":
        # Felipe et al. 2014 / Ceselli et al. 2021: minimize recharge cost, not distance.
        fixed = float(spec.metadata.get("fixed_recharge_cost") or 0.0)
        variable = 0.0
        operations = 0
        type_ids = list(assignments)
        by_id = {v.type_id: v for v in spec.vehicle_types}
        for traj, type_id in zip(trajectories, type_ids, strict=True):
            vehicle = by_id.get(type_id)
            techs = {} if vehicle is None else (vehicle.metadata.get("charging_techs") or {})
            for state in traj:
                if state.energy_charged <= EPSILON:
                    continue
                tech_key = str(state.charge_technology) if state.charge_technology is not None else "0"
                gamma = float(techs.get(tech_key, {}).get("gamma", 0.0))
                variable += gamma * state.energy_charged
                operations += 1
        cost = fixed * operations + variable
        report.objective_key = (cost,)
        report.objective_components = {
            "recharge_cost": cost,
            "fixed_recharge_cost": fixed * operations,
            "variable_recharge_cost": variable,
            "recharge_operations": float(operations),
            "matrix_travel": distance,
            "total_duration": duration,
        }
    elif spec.family == "hiermann":
        prices = spec.metadata.get("energy_prices") or {}
        fossil = float(prices.get("fossil-fuel", 0.0))
        elec = float(prices.get("electricity", 0.0))
        fuel = sum(traj[-1].fuel_used for traj in trajectories if traj)
        electric = sum(traj[-1].electric_used for traj in trajectories if traj)
        fixed = 0.0
        type_ids = list(assignments)
        for type_id in type_ids:
            fixed += next((v.fixed_cost for v in spec.vehicle_types if v.type_id == type_id), 0.0)
        cost = fixed + fossil * fuel + elec * electric
        report.objective_key = (cost,)
        report.objective_components = {
            "fixed_cost": fixed,
            "fuel_used": fuel,
            "electric_used": electric,
            "energy_cost": fossil * fuel + elec * electric,
            "total_cost": cost,
        }
    else:
        report.objective_key = (distance, duration)
        report.objective_components = {"distance": distance, "duration": duration}
    report.objective = report.objective_key[0] if report.objective_key else None


def evaluate_solution_v2(spec: ProblemSpecV2, solution: SolutionV2) -> EvaluationReportV2:
    """Canonical trusted evaluator for all v2 families."""
    started = time.monotonic()
    report = EvaluationReportV2(family=spec.family, vehicles=len(solution.routes))
    if not spec.depot_ids:
        report.parse_ok = False
        report.error = "spec missing depot"
        report.add("PARSE", detail=report.error)
        report.runtime_s = time.monotonic() - started
        return report

    served: list[str] = []
    required = set(_required_visit_ids(spec))
    max_travel = None
    if spec.vehicle_types:
        max_travel = spec.vehicle_types[0].metadata.get("max_travel_time")
    if max_travel is None:
        max_travel = spec.metadata.get("max_travel_time")

    resolved_ids: list[str] = []
    try:
        for route_index, route in enumerate(solution.routes):
            vehicle = _vehicle_for_route(spec, solution, route_index, route)
            resolved_ids.append(vehicle.type_id)
            _check_depot(spec, route, route_index, report, vehicle)
            # Fleet availability (soft count later; hard if finite and exceeded tracked via Counter at end).
            _check_pd_precedence(spec, route, route_index, report)
            traj, charge_errs = simulate_route(spec, route, vehicle)
            report.trajectories.append(traj)
            for err in charge_errs:
                report.add("CHARGE_POLICY", route_index=route_index, detail=err)
            if traj:
                report.total_distance += traj[-1].distance_so_far
                report.total_duration += traj[-1].departure_time
            capacity = vehicle.capacity
            battery_cap = vehicle.battery_capacity
            uses_battery = (vehicle.is_electric or vehicle.is_hybrid) and battery_cap is not None

            for stop_state, _stop in zip(traj, route, strict=True):
                node = spec.node_map[stop_state.node_id]
                if node.kind in {"customer", "pickup", "delivery"}:
                    served.append(node.id)
                    if spec.capabilities.time_windows and stop_state.service_start > node.due_time + EPSILON:
                        lateness = stop_state.service_start - node.due_time
                        report.add(
                            "WINDOW",
                            node_id=node.id,
                            route_index=route_index,
                            detail=(
                                f"service_start={stop_state.service_start:.6f} "
                                f"due={node.due_time:.6f} lateness={lateness:.6f}"
                            ),
                            magnitude=lateness,
                        )
                if capacity is not None and stop_state.load > capacity + EPSILON:
                    excess = stop_state.load - capacity
                    report.add(
                        "CAPACITY",
                        node_id=node.id,
                        route_index=route_index,
                        detail=f"load={stop_state.load:.6f} capacity={capacity:.6f}",
                        magnitude=excess,
                    )
                if stop_state.load < -EPSILON:
                    report.add(
                        "CAPACITY",
                        node_id=node.id,
                        route_index=route_index,
                        detail=f"negative_load={stop_state.load:.6f}",
                        magnitude=abs(stop_state.load),
                    )
                if uses_battery and battery_cap is not None:
                    if stop_state.battery_arrival < -EPSILON or stop_state.battery_departure < -EPSILON:
                        deficit = abs(min(stop_state.battery_arrival, stop_state.battery_departure))
                        report.add(
                            "BATTERY",
                            node_id=node.id,
                            route_index=route_index,
                            detail=(
                                f"battery_arrival={stop_state.battery_arrival:.6f} "
                                f"battery_departure={stop_state.battery_departure:.6f}"
                            ),
                            magnitude=deficit,
                        )
                    if stop_state.battery_departure > float(battery_cap) + EPSILON:
                        report.add(
                            "BATTERY",
                            node_id=node.id,
                            route_index=route_index,
                            detail="battery above capacity",
                        )
                if node.kind == "station":
                    report.charging_visits += 1

            # Depot due / max route duration.
            if traj and spec.capabilities.time_windows:
                depot = spec.node_map[spec.depot_ids[0]]
                if traj[-1].arrival_time > depot.due_time + EPSILON:
                    lateness = traj[-1].arrival_time - depot.due_time
                    report.add(
                        "WINDOW",
                        node_id=depot.id,
                        route_index=route_index,
                        detail=(
                            f"depot return arrival={traj[-1].arrival_time:.6f} "
                            f"due={depot.due_time:.6f}"
                        ),
                        magnitude=lateness,
                    )
            route_limit = vehicle.metadata.get("max_travel_time", max_travel)
            if traj and route_limit is not None and traj[-1].departure_time > float(route_limit) + EPSILON:
                excess = traj[-1].departure_time - float(route_limit)
                report.add(
                    "DURATION",
                    node_id=spec.depot_ids[0],
                    route_index=route_index,
                    detail=(
                        f"route_duration={traj[-1].departure_time:.6f} "
                        f"max_travel_time={float(route_limit):.6f}"
                    ),
                    magnitude=excess,
                )
    except (KeyError, ValueError, TypeError) as error:
        report.parse_ok = False
        report.error = str(error)
        report.add("PARSE", detail=str(error)[:400])
        report.runtime_s = time.monotonic() - started
        report.explanation = report.error
        return report

    counts = Counter(served)
    report.duplicates = [cid for cid, n in counts.items() if n > 1]
    report.unserved = sorted(cid for cid in required if cid not in counts)
    extras = sorted(cid for cid in counts if cid not in required)
    for cid in report.duplicates:
        report.add("VISIT", node_id=cid, detail="served more than once")
    for cid in report.unserved:
        report.add("VISIT", node_id=cid, detail="never served")
    for cid in extras:
        report.add("VISIT", node_id=cid, detail="unexpected visit id")

    # Same-vehicle completeness for PD: every request both ends present on some route.
    if spec.capabilities.pickup_delivery:
        for req in spec.requests:
            if req.pickup_id not in counts or req.delivery_id not in counts:
                # Already covered by unserved usually; keep explicit pairing family.
                if req.pickup_id not in counts or req.delivery_id not in counts:
                    report.add(
                        "PAIRING",
                        node_id=req.request_id,
                        detail=f"incomplete request {req.request_id}",
                    )

    # Count every actual route's resolved vehicle type, not only an incomplete assignment list.
    resolved_types: list[str] = []
    for route_index, route in enumerate(solution.routes):
        try:
            resolved_types.append(_vehicle_for_route(spec, solution, route_index, route).type_id)
        except ValueError as error:
            report.add("FLEET", route_index=route_index, detail=str(error)[:200])
    used_types = Counter(resolved_types)
    for type_id, count in used_types.items():
        limit = spec.fleet_availability.get(type_id)
        if limit is None or limit >= 10**8:
            continue
        if count > int(limit):
            report.add(
                "FLEET",
                detail=f"vehicle type {type_id} used {count} times; available {limit}",
                magnitude=float(count - int(limit)),
            )

    hard_families = {
        "PARSE",
        "DEPOT",
        "VISIT",
        "CAPACITY",
        "WINDOW",
        "BATTERY",
        "CHARGE_POLICY",
        "PRECEDENCE",
        "PAIRING",
        "DURATION",
        "FLEET",
    }
    hard = [v for v in report.violations if v.family in hard_families]
    report.feasible = report.parse_ok and not hard
    _objective(spec, report, report.trajectories, resolved_ids)
    if report.first_fault is None:
        from evrptw_autolab.problem.v2.report import ViolationV2

        report.first_fault = ViolationV2("OK", detail="feasible" if report.feasible else "unknown")
    if report.feasible:
        report.explanation = "all hard constraints satisfied"
    else:
        fault = report.first_fault
        report.explanation = f"{fault.family}: {fault.detail}" if fault else "infeasible"
    report.runtime_s = time.monotonic() - started
    return report
