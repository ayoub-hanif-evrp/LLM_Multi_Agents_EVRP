"""Apply bounded agent actions. This module does not search or call ALNS."""
from __future__ import annotations

from typing import Any

from evrptw_autolab.agentic_v2.instance_context import customer_ids
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2


def _event_for(spec: ProblemSpecV2, node_id: str) -> str:
    kind = spec.node_map[node_id].kind
    if kind == "pickup":
        return "pickup"
    if kind == "delivery":
        return "delivery"
    if kind == "station":
        return "charge"
    if kind == "depot":
        return "depot"
    return "visit"


def _vehicle_type(spec: ProblemSpecV2, requested: object) -> str:
    known = {vehicle.type_id for vehicle in spec.vehicle_types}
    text = str(requested or "")
    if text in known:
        return text
    return spec.vehicle_types[0].type_id if spec.vehicle_types else ""


def solution_from_plan(spec: ProblemSpecV2, payload: dict[str, Any]) -> tuple[SolutionV2, list[str]]:
    """Build a SolutionV2 from explicit routes. Unknown ids are rejected, not invented."""
    errors: list[str] = []
    depot = spec.depot_ids[0] if spec.depot_ids else ""
    routes: list[list[RouteStopV2]] = []
    assignments: list[str] = []
    seen: list[str] = []
    for raw in payload.get("routes") or []:
        if not isinstance(raw, dict):
            errors.append("route_not_object")
            continue
        vehicle = _vehicle_type(spec, raw.get("vehicle_type"))
        stops = [RouteStopV2(depot, vehicle, "depot")]
        customers = raw.get("stops") or raw.get("customers") or []
        for item in customers:
            node_id = str(item.get("node_id") if isinstance(item, dict) else item)
            if node_id not in spec.node_map:
                errors.append(f"unknown_node:{node_id}")
                continue
            if node_id == depot or spec.node_map[node_id].kind == "station":
                if spec.node_map[node_id].kind == "station":
                    errors.append(f"station_left_for_charging_agent:{node_id}")
                continue
            event = _event_for(spec, node_id)
            charge_amount = None
            technology = None
            target = None
            if isinstance(item, dict) and event == "charge":
                if item.get("charge_amount") is not None:
                    charge_amount = float(item["charge_amount"])
                if item.get("charge_technology") is not None:
                    technology = str(item["charge_technology"])
                if item.get("target_soc") is not None:
                    target = float(item["target_soc"])
            stops.append(
                RouteStopV2(
                    node_id,
                    vehicle,
                    event,  # type: ignore[arg-type]
                    charge_amount=charge_amount,
                    charge_technology=technology,
                    target_soc=target,
                )
            )
            if spec.node_map[node_id].kind in {"customer", "pickup", "delivery"}:
                seen.append(node_id)
        stops.append(RouteStopV2(depot, vehicle, "depot"))
        if len(stops) > 2:
            routes.append(stops)
            assignments.append(vehicle)
    required = customer_ids(spec)
    missing = [node_id for node_id in required if node_id not in seen]
    if missing:
        errors.append("missing_customers:" + ",".join(missing[:12]))
    if not routes:
        errors.append("no_routes")
        routes = [[RouteStopV2(depot, assignments[0] if assignments else None, "depot"), RouteStopV2(depot, None, "depot")]]
    solution = SolutionV2(
        routes=routes,
        vehicle_assignments=assignments,
        metadata={"method": "agentic_v2", "attribution": "agent_routes", "classical_alns": False},
    )
    return solution, errors


def insert_charges(spec: ProblemSpecV2, solution: SolutionV2, payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for item in payload.get("insertions") or []:
        if not isinstance(item, dict):
            errors.append("insertion_not_object")
            continue
        route_index = int(item.get("route", 0))
        station_id = str(item.get("station_id") or "")
        after_node = str(item.get("after_stop") or "")
        if station_id not in spec.node_map or spec.node_map[station_id].kind != "station":
            errors.append(f"unknown_station:{station_id}")
            continue
        if route_index < 0 or route_index >= len(solution.routes):
            errors.append(f"bad_route:{route_index}")
            continue
        route = solution.routes[route_index]
        position = next((index for index, stop in enumerate(route) if stop.node_id == after_node), None)
        if position is None:
            errors.append(f"after_stop_missing:{after_node}")
            continue
        vehicle = route[0].vehicle_type_id
        amount = None if item.get("charge_amount") is None else float(item["charge_amount"])
        target = None if item.get("target_soc") is None else float(item["target_soc"])
        technology = None if item.get("charge_technology") is None else str(item["charge_technology"])
        route.insert(
            position + 1,
            RouteStopV2(
                station_id,
                vehicle,
                "charge",
                charge_amount=amount,
                charge_technology=technology,
                target_soc=target,
            ),
        )
    return errors


def apply_relocations(spec: ProblemSpecV2, solution: SolutionV2, payload: dict[str, Any]) -> list[str]:
    """Apply at most four customer relocations. Other operations are ignored."""
    errors: list[str] = []
    applied = 0
    for item in payload.get("moves") or []:
        if applied >= 4:
            errors.append("move_budget_exhausted")
            break
        if not isinstance(item, dict) or item.get("op") not in {None, "relocate"}:
            errors.append("unsupported_move")
            continue
        customer = str(item.get("customer") or "")
        if customer not in spec.node_map:
            errors.append(f"unknown_customer:{customer}")
            continue
        destination = int(item.get("to_route", 0))
        if destination < 0 or destination >= len(solution.routes):
            errors.append(f"bad_route:{destination}")
            continue
        removed: RouteStopV2 | None = None
        for route in solution.routes:
            for index, stop in enumerate(list(route)):
                if stop.node_id == customer and stop.event != "depot":
                    removed = route.pop(index)
                    break
            if removed is not None:
                break
        if removed is None:
            errors.append(f"customer_not_in_solution:{customer}")
            continue
        position = int(item.get("position", 1))
        route = solution.routes[destination]
        position = max(1, min(position, len(route) - 1))
        route.insert(position, removed)
        applied += 1
    return errors
