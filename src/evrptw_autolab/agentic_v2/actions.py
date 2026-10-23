"""Apply bounded agent actions. This module does not search or call ALNS."""
from __future__ import annotations

import copy
from typing import Any

from evrptw_autolab.agentic_v2.instance_context import customer_ids
from evrptw_autolab.problem.v2.evaluator import evaluate_solution_v2
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
        raw_charge = raw.get("depot_charge")
        depot_charge: dict[str, Any] = raw_charge if isinstance(raw_charge, dict) else {}
        amount = None if depot_charge.get("charge_amount") is None else float(depot_charge["charge_amount"])
        technology = None if depot_charge.get("charge_technology") is None else str(depot_charge["charge_technology"])
        stops = [
            RouteStopV2(depot, vehicle, "depot", charge_amount=amount, charge_technology=technology)
        ]
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


_ALLOWED_WHERE = {None, "", "departure_depot"}
_ALLOWED_MOVE = {None, "relocate"}


def validate_action_payload(payload: dict[str, Any]) -> list[str]:
    """Reject a malformed action before any route is edited."""
    errors: list[str] = []
    for item in payload.get("insertions") or []:
        if not isinstance(item, dict):
            errors.append("insertion_not_object")
            continue
        where = item.get("where")
        if where not in _ALLOWED_WHERE:
            errors.append(f"malformed_where:{where}")
            continue
        if where == "departure_depot":
            if item.get("charge_amount") is None and item.get("target_soc") is None:
                errors.append("depot_charge_missing_amount")
            continue
        if not str(item.get("station_id") or ""):
            errors.append("missing_station_id")
        if item.get("after_index") is None and not str(item.get("after_stop") or ""):
            errors.append("missing_after_stop")
    for item in payload.get("moves") or []:
        if not isinstance(item, dict):
            errors.append("move_not_object")
            continue
        if item.get("op") not in _ALLOWED_MOVE:
            errors.append(f"malformed_op:{item.get('op')}")
    return errors


def insert_charges(spec: ProblemSpecV2, solution: SolutionV2, payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for item in payload.get("insertions") or []:
        if not isinstance(item, dict):
            errors.append("insertion_not_object")
            continue
        route_index = int(item.get("route", 0))
        if route_index < 0 or route_index >= len(solution.routes):
            errors.append(f"bad_route:{route_index}")
            continue
        route = solution.routes[route_index]
        vehicle = route[0].vehicle_type_id
        amount = None if item.get("charge_amount") is None else float(item["charge_amount"])
        target = None if item.get("target_soc") is None else float(item["target_soc"])
        technology = None if item.get("charge_technology") is None else str(item["charge_technology"])
        if str(item.get("where") or "") == "departure_depot":
            origin = route[0]
            route[0] = RouteStopV2(
                origin.node_id,
                vehicle,
                "depot",
                charge_amount=amount,
                charge_technology=technology,
                target_soc=target,
            )
            continue
        station_id = str(item.get("station_id") or "")
        after_node = str(item.get("after_stop") or "")
        if station_id not in spec.node_map or spec.node_map[station_id].kind != "station":
            errors.append(f"unknown_station:{station_id}")
            continue
        if item.get("after_index") is not None:
            position = int(item["after_index"])
            if position < 0 or position >= len(route) - 1:
                errors.append(f"bad_after_index:{position}")
                continue
        else:
            matches = [index for index, stop in enumerate(route) if stop.node_id == after_node]
            if len(matches) != 1:
                errors.append(f"ambiguous_or_missing_after_stop:{after_node}")
                continue
            position = matches[0]
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


def _paired_ids(spec: ProblemSpecV2, node_id: str) -> list[str]:
    if not spec.capabilities.pickup_delivery:
        return [node_id]
    for request in spec.requests:
        if node_id in {request.pickup_id, request.delivery_id} and request.same_vehicle:
            return [request.pickup_id, request.delivery_id]
    return [node_id]


def apply_relocations(spec: ProblemSpecV2, solution: SolutionV2, payload: dict[str, Any]) -> list[str]:
    """Apply at most four relocations. A pickup-delivery pair moves together."""
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
        wanted = _paired_ids(spec, customer)
        removed: list[RouteStopV2] = []
        for node_id in wanted:
            found: RouteStopV2 | None = None
            for route in solution.routes:
                for index, stop in enumerate(list(route)):
                    if stop.node_id == node_id and stop.event != "depot":
                        found = route.pop(index)
                        break
                if found is not None:
                    break
            if found is None:
                errors.append(f"customer_not_in_solution:{node_id}")
            else:
                removed.append(found)
        if len(removed) != len(wanted):
            continue
        route = solution.routes[destination]
        position = max(1, min(int(item.get("position", 1)), len(route) - 1))
        for offset, stop in enumerate(removed):
            route.insert(position + offset, stop)
        applied += 1
    return errors


def _clone_solution(solution: SolutionV2) -> SolutionV2:
    return SolutionV2(
        routes=copy.deepcopy(solution.routes),
        vehicle_assignments=list(solution.vehicle_assignments),
        metadata=dict(solution.metadata),
    )


def apply_transaction(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    payload: dict[str, Any],
    *,
    acceptance: str = "incumbent",
) -> tuple[SolutionV2, list[str], bool]:
    """Clone, apply, and commit only under the named acceptance policy.

    ``incumbent`` keeps a feasible trial only when its native objective is no worse.
    ``explore`` may accept a feasible but worse trial. The caller still stores the
    best feasible solution separately.
    """
    schema_errors = validate_action_payload(payload)
    if schema_errors:
        return _clone_solution(solution), schema_errors, False
    trial = _clone_solution(solution)
    errors = insert_charges(spec, trial, payload)
    errors.extend(apply_relocations(spec, trial, payload))
    if errors:
        return _clone_solution(solution), errors, False
    before = evaluate_solution_v2(spec, solution)
    after = evaluate_solution_v2(spec, trial)
    if not after.feasible:
        return _clone_solution(solution), ["rejected_infeasible_trial"], False
    worse = before.feasible and tuple(after.objective_key) > tuple(before.objective_key)
    if worse and acceptance != "explore":
        return _clone_solution(solution), ["rejected_objective_regression"], False
    trial.metadata["classical_alns"] = False
    trial.metadata["acceptance"] = acceptance
    return trial, [], True
