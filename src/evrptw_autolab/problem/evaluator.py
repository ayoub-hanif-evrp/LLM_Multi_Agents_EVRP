"""Independent canonical evaluator. Does not construct or search routes."""
from __future__ import annotations

from collections import Counter
from typing import Any

from evrptw_autolab.problem.physics import EPSILON, propagate_route, validate_full_recharge
from evrptw_autolab.problem.types import CandidateSolution, EvaluationReport, EVRPTWInstance

OK_FAULT = {"family": "OK", "node_id": "", "route_index": -1, "detail": ""}


def _packet(family: str, *, node_id: str = "", route_index: int = -1, detail: str = "") -> dict[str, Any]:
    return {"family": family, "node_id": node_id, "route_index": route_index, "detail": detail}


def first_fault(instance: EVRPTWInstance, solution: CandidateSolution) -> dict[str, Any]:
    """Lab oracle: the first violated family, with the node that failed. Not a solver."""
    served: list[str] = []
    nodes = instance.node_map
    try:
        for route_index, route in enumerate(solution.routes):
            if not route or route[0] != instance.depot_id or route[-1] != instance.depot_id:
                node_id = route[0] if route else ""
                return _packet("DEPOT", node_id=str(node_id), route_index=route_index, detail="route must start and end at depot_id")
            stops = propagate_route(instance, route)
            for stop in stops:
                node = nodes[stop.node_id]
                if node.kind == "customer":
                    served.append(node.id)
                    if stop.service_start > node.due_time + EPSILON:
                        # Find previous node on this route for diagnostics.
                        prev = ""
                        for i, nid in enumerate(route):
                            if nid == node.id and i > 0:
                                prev = str(route[i - 1])
                                break
                        lateness = float(stop.service_start - node.due_time)
                        return {
                            "family": "WINDOW",
                            "node_id": node.id,
                            "route_index": route_index,
                            "detail": (
                                f"service_start={stop.service_start:.3f} due={node.due_time:.3f} "
                                f"lateness={lateness:.3f} previous={prev}"
                            ),
                            "arrival": float(stop.arrival_time),
                            "service_start": float(stop.service_start),
                            "due_time": float(node.due_time),
                            "lateness": lateness,
                            "previous_node": prev,
                            "route": list(route),
                        }
                if stop.load > instance.vehicle.capacity + EPSILON:
                    return _packet(
                        "CAPACITY",
                        node_id=node.id,
                        route_index=route_index,
                        detail=f"load={stop.load:.3f} capacity={instance.vehicle.capacity:.3f}",
                    )
                if stop.battery_arrival < -EPSILON or stop.battery_departure < -EPSILON:
                    return _packet(
                        "BATTERY",
                        node_id=node.id,
                        route_index=route_index,
                        detail=f"battery_arrival={stop.battery_arrival:.3f}",
                    )
                if stop.battery_departure > instance.vehicle.battery_capacity + EPSILON:
                    return _packet(
                        "BATTERY",
                        node_id=node.id,
                        route_index=route_index,
                        detail="battery above capacity",
                    )
                if node.kind == "station":
                    charge_errors = validate_full_recharge(
                        instance.vehicle, stop.battery_arrival, stop.energy_charged
                    )
                    if charge_errors:
                        return _packet(
                            "CHARGE_POLICY",
                            node_id=node.id,
                            route_index=route_index,
                            detail=charge_errors[0],
                        )
            if stops and stops[-1].arrival_time > instance.depot.due_time + EPSILON:
                prev = str(route[-2]) if len(route) >= 2 else ""
                lateness = float(stops[-1].arrival_time - instance.depot.due_time)
                return {
                    "family": "WINDOW",
                    "node_id": instance.depot_id,
                    "route_index": route_index,
                    "detail": (
                        f"return depot arrival={stops[-1].arrival_time:.3f} "
                        f"due={instance.depot.due_time:.3f} lateness={lateness:.3f} previous={prev}"
                    ),
                    "arrival": float(stops[-1].arrival_time),
                    "service_start": float(stops[-1].service_start),
                    "due_time": float(instance.depot.due_time),
                    "lateness": lateness,
                    "previous_node": prev,
                    "route": list(route),
                }
    except (KeyError, ValueError) as error:
        return _packet("PARSE", detail=str(error)[:400])

    counts = Counter(served)
    duplicates = [cid for cid, n in counts.items() if n > 1]
    if duplicates:
        return _packet("VISIT", node_id=duplicates[0], detail="customer served more than once")
    unserved = [cid for cid in instance.customer_ids if cid not in counts]
    if unserved:
        return _packet("VISIT", node_id=unserved[0], detail="customer never served")
    extra = [cid for cid in counts if cid not in instance.customer_ids]
    if extra:
        return _packet("VISIT", node_id=extra[0], detail="unknown customer id in routes")
    return dict(OK_FAULT)


def evaluate_solution(instance: EVRPTWInstance, solution: CandidateSolution) -> EvaluationReport:
    report = EvaluationReport(vehicles=len(solution.routes))
    served: list[str] = []
    nodes = instance.node_map
    try:
        for route in solution.routes:
            if not route or route[0] != instance.depot_id or route[-1] != instance.depot_id:
                report.depot_violations += 1
            stops = propagate_route(instance, route)
            report.total_distance += stops[-1].distance_so_far if stops else 0.0
            for stop in stops:
                node = nodes[stop.node_id]
                if node.kind == "customer":
                    served.append(node.id)
                    if stop.service_start > node.due_time + EPSILON:
                        report.time_window_violations += 1
                if stop.load > instance.vehicle.capacity + EPSILON:
                    report.capacity_violations += 1
                if stop.battery_arrival < -EPSILON or stop.battery_departure < -EPSILON:
                    report.battery_violations += 1
                if stop.battery_departure > instance.vehicle.battery_capacity + EPSILON:
                    report.battery_violations += 1
                if node.kind == "station":
                    report.charging_visits += 1
                    report.charging_violations += len(
                        validate_full_recharge(
                            instance.vehicle, stop.battery_arrival, stop.energy_charged
                        )
                    )
            if stops and stops[-1].arrival_time > instance.depot.due_time + EPSILON:
                report.depot_violations += 1
    except (KeyError, ValueError) as error:
        report.parse_ok = False
        report.error = str(error)
        report.first_fault = _packet("PARSE", detail=str(error)[:400])
        return report

    counts = Counter(served)
    report.duplicates = [cid for cid, n in counts.items() if n > 1]
    report.unserved = [cid for cid in instance.customer_ids if cid not in counts]
    extra = [cid for cid in counts if cid not in instance.customer_ids]
    report.all_customers_served_once = (
        not report.unserved and not report.duplicates and not extra
    )
    report.feasible = (
        report.parse_ok
        and report.all_customers_served_once
        and report.capacity_violations == 0
        and report.time_window_violations == 0
        and report.battery_violations == 0
        and report.charging_violations == 0
        and report.depot_violations == 0
    )
    report.first_fault = first_fault(instance, solution)
    report.routes = [list(r) for r in solution.routes]
    return report
