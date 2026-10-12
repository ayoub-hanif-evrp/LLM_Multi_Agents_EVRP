"""Deterministic failure measurements for generated solvers. No repair advice."""
from __future__ import annotations

import re
from typing import Any

from evrptw_autolab.problem.physics import EPSILON, propagate_route
from evrptw_autolab.problem.types import EvaluationReport, EVRPTWInstance


def format_runtime_error(error: str, source: str = "") -> dict[str, Any]:
    """Keep the exception at the bottom of a traceback, not the opening banner."""
    lines = [line.rstrip() for line in (error or "").splitlines() if line.strip()]
    lines = [line for line in lines if not line.startswith("CONTRACT:")]
    tail = lines[-8:]
    exception_type = ""
    exception_message = ""
    for line in reversed(tail):
        stripped = line.strip()
        if stripped.startswith("Traceback") or stripped.startswith("File ") or stripped.startswith("raise "):
            continue
        if ":" in stripped and not stripped.startswith("File"):
            exception_type, exception_message = stripped.split(":", 1)
            exception_type = exception_type.strip().split()[-1]
            exception_message = exception_message.strip()
            break
    context = ""
    numbers = [int(match) for match in re.findall(r"line (\d+)", "\n".join(tail))]
    if numbers and source:
        lineno = numbers[-1]
        rows = source.splitlines()
        start = max(0, lineno - 3)
        end = min(len(rows), lineno + 2)
        context = "\n".join(f"{index + 1}: {rows[index]}" for index in range(start, end))
    return {
        "exception_type": exception_type,
        "exception_message": exception_message,
        "traceback_tail": "\n".join(tail),
        "source_context": context,
    }


def _state_row(stop: Any) -> dict[str, Any]:
    return {
        "node_id": str(stop.node_id),
        "arrival_time": float(stop.arrival_time),
        "service_start": float(stop.service_start),
        "load": float(stop.load),
        "battery_arrival": float(stop.battery_arrival),
        "battery_departure": float(stop.battery_departure),
    }


def _route_metrics(instance: EVRPTWInstance, route: list[str]) -> dict[str, Any]:
    """Measurements for one route. Never suggests how to repair."""
    capacity_excess = 0.0
    battery_deficit = 0.0
    lateness = 0.0
    depot_violations = 0
    states: list[dict[str, Any]] = []
    failed_node = ""
    family = ""
    if not route or route[0] != instance.depot_id or route[-1] != instance.depot_id:
        depot_violations = 1
        family = "DEPOT"
        failed_node = str(route[0] if route else "")
        return {
            "family": family,
            "route": list(route),
            "failed_node": failed_node,
            "depot_violations": depot_violations,
            "capacity_excess": 0.0,
            "battery_deficit": 0.0,
            "lateness": 0.0,
            "states": [],
        }
    if instance.depot_id in route[1:-1]:
        depot_violations = 1
        family = "DEPOT"
        failed_node = instance.depot_id
    try:
        stops = propagate_route(instance, route)
    except (KeyError, ValueError, TypeError) as error:
        return {
            "family": "PARSE",
            "route": list(route),
            "failed_node": "",
            "depot_violations": depot_violations,
            "capacity_excess": 0.0,
            "battery_deficit": 0.0,
            "lateness": 0.0,
            "states": [],
            "detail": str(error)[:400],
        }
    states = [_state_row(stop) for stop in stops]
    nodes = instance.node_map
    for stop in stops:
        node = nodes[stop.node_id]
        if stop.load > instance.vehicle.capacity + EPSILON:
            excess = float(stop.load - instance.vehicle.capacity)
            if excess > capacity_excess:
                capacity_excess = excess
                if not family:
                    family = "CAPACITY"
                    failed_node = node.id
        if stop.battery_arrival < -EPSILON:
            deficit = float(-stop.battery_arrival)
            if deficit > battery_deficit:
                battery_deficit = deficit
                if not family:
                    family = "BATTERY"
                    failed_node = node.id
        if node.kind == "customer" and stop.service_start > node.due_time + EPSILON:
            late = float(stop.service_start - node.due_time)
            if late > lateness:
                lateness = late
                if not family:
                    family = "WINDOW"
                    failed_node = node.id
    if stops and stops[-1].arrival_time > instance.depot.due_time + EPSILON:
        late = float(stops[-1].arrival_time - instance.depot.due_time)
        if late > lateness:
            lateness = late
            if not family:
                family = "WINDOW"
                failed_node = instance.depot_id
    return {
        "family": family,
        "route": list(route),
        "failed_node": failed_node,
        "depot_violations": depot_violations,
        "capacity_excess": round(capacity_excess, 4),
        "battery_deficit": round(battery_deficit, 4),
        "lateness": round(lateness, 4),
        "states": states,
    }


def solution_diagnostic(
    report: EvaluationReport,
    *,
    source: str = "",
    instance: EVRPTWInstance | None = None,
) -> dict[str, Any]:
    """Execution evidence only. Never names a station or insertion method."""
    syntax_valid = bool(report.parse_ok) and not bool(report.crashed)
    out: dict[str, Any] = {
        "crashed": bool(report.crashed or report.timed_out or not report.parse_ok),
        "syntax_valid": syntax_valid,
        "timed_out": bool(report.timed_out),
        "family": str((report.first_fault or {}).get("family") or ""),
        "route": [],
        "failed_node": str((report.first_fault or {}).get("node_id") or ""),
        "customers_missing": list(report.unserved or []),
        "customers_duplicated": list(report.duplicates or []),
        "depot_violations": int(report.depot_violations or 0),
        "capacity_excess": 0.0,
        "battery_deficit": 0.0,
        "lateness": 0.0,
        "charging_policy_violation": int(report.charging_violations or 0),
        "states": [],
        "detail": str((report.first_fault or {}).get("detail") or report.error or ""),
    }
    if report.crashed or report.timed_out or not report.parse_ok:
        execution = format_runtime_error(str(report.error or ""), source)
        out["exception_type"] = execution.get("exception_type") or ""
        out["exception_message"] = execution.get("exception_message") or ""
        out["traceback_tail"] = execution.get("traceback_tail") or ""
        out["source_context"] = execution.get("source_context") or ""
        return out

    routes = [list(route) for route in (report.routes or [])]
    fault = dict(report.first_fault or {})
    route_index = int(fault.get("route_index", -1))
    if instance is None:
        if 0 <= route_index < len(routes):
            out["route"] = routes[route_index]
        out["customers_missing"] = list(report.unserved or [])
        out["customers_duplicated"] = list(report.duplicates or [])
        return out

    total_capacity = 0.0
    total_battery = 0.0
    total_late = 0.0
    total_depot = 0
    chosen: dict[str, Any] | None = None
    for index, route in enumerate(routes):
        metrics = _route_metrics(instance, route)
        total_capacity += float(metrics["capacity_excess"])
        total_battery += float(metrics["battery_deficit"])
        total_late += float(metrics["lateness"])
        total_depot += int(metrics["depot_violations"])
        if chosen is None and (index == route_index or (route_index < 0 and metrics["family"])):
            chosen = metrics
        if index == route_index:
            chosen = metrics
    if chosen is None and routes:
        chosen = _route_metrics(instance, routes[0])
    if chosen:
        out["route"] = list(chosen.get("route") or [])
        out["failed_node"] = str(chosen.get("failed_node") or out["failed_node"])
        out["states"] = list(chosen.get("states") or [])
        if chosen.get("family"):
            out["family"] = str(chosen["family"])
    out["depot_violations"] = max(int(report.depot_violations or 0), total_depot)
    out["capacity_excess"] = round(total_capacity, 4)
    out["battery_deficit"] = round(total_battery, 4)
    out["lateness"] = round(total_late, 4)
    out["customers_missing"] = list(report.unserved or [])
    out["customers_duplicated"] = list(report.duplicates or [])
    return out


def progress_key(info: dict[str, Any]) -> tuple:
    """Higher is better for STAGE_BEST among failed candidates."""
    diagnostic = dict(info.get("diagnostic") or {})
    return (
        int(info.get("gates_passed") or 0),
        int(info.get("instances_feasible") or 0),
        -int(len(diagnostic.get("customers_missing") or []) + len(diagnostic.get("customers_duplicated") or [])),
        -int(diagnostic.get("depot_violations") or 0),
        -float(diagnostic.get("capacity_excess") or 0.0),
        -float(diagnostic.get("battery_deficit") or 0.0),
        -float(diagnostic.get("lateness") or 0.0),
    )
