"""Load a published instance and describe it without changing the benchmark."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from evrptw_autolab.problem.datasets.registry import (
    DATASET_ROOT,
    DATASET_SPECS,
    _loader_for,
    _match_instances,
)
from evrptw_autolab.problem.v2.types import ProblemSpecV2

OBJECTIVES: dict[str, str] = {
    "schneider": "minimize vehicle count, then travel distance",
    "goeke": "minimize vehicle count, then travel distance",
    "montoya": "minimize total route duration",
    "bezzi": "minimize recharge cost; every station stop needs an explicit charge amount and technology",
    "hiermann": "minimize fixed vehicle cost plus fuel and electricity cost",
    "micro": "minimize distance, then duration",
}

_FAULT_AGENT = {
    "VISIT": "routing",
    "DEPOT": "routing",
    "CAPACITY": "routing",
    "WINDOW": "routing",
    "PRECEDENCE": "routing",
    "PAIRING": "routing",
    "FLEET": "routing",
    "BATTERY": "charging",
    "CHARGE_POLICY": "charging",
    "DURATION": "optimization",
}


def native_objective(family: str) -> str:
    return OBJECTIVES.get(family, "minimize the family's native objective")


def problem_context(spec: ProblemSpecV2, *, include_matrices: bool = True) -> dict[str, Any]:
    """Serializable inputs a charging or routing decision needs. No hidden solution."""
    caps = spec.capabilities
    technologies = []
    for vehicle in spec.vehicle_types:
        technologies.append(
            {
                "type_id": vehicle.type_id,
                "battery_capacity": vehicle.battery_capacity,
                "consumption_rate": vehicle.consumption_rate,
                "fixed_cost": vehicle.fixed_cost,
                "variable_cost": vehicle.variable_cost,
                "departure_node": vehicle.metadata.get("departure_node"),
                "arrival_node": vehicle.metadata.get("arrival_node"),
                "charging_techs": vehicle.metadata.get("charging_techs") or {},
                "charging_functions": vehicle.metadata.get("charging_functions") or {},
            }
        )
    context: dict[str, Any] = {
        "native_objective": native_objective(spec.family),
        "initial_battery_rule": (
            "empty_until_explicit_depot_charge"
            if caps.multiple_charge_technologies
            else "start_at_battery_capacity"
        ),
        "uses_published_matrices": bool(caps.matrix_distances),
        "euclidean_distances": bool(caps.euclidean_distances),
        "fleet_availability": dict(spec.fleet_availability),
        "fixed_recharge_cost": spec.metadata.get("fixed_recharge_cost"),
        "energy_prices": spec.metadata.get("energy_prices"),
        "nonlinear_curves": spec.metadata.get("charging_functions"),
        "vehicles": technologies,
        "requests": [
            {
                "request_id": request.request_id,
                "pickup_id": request.pickup_id,
                "delivery_id": request.delivery_id,
                "demand": request.demand,
                "same_vehicle": request.same_vehicle,
            }
            for request in spec.requests
        ],
    }
    if include_matrices and caps.matrix_distances:
        context["energy_matrix"] = spec.metadata.get("energy_matrix")
        context["travel_time_matrix"] = spec.metadata.get("travel_time_matrix")
        context["distance_matrix"] = spec.metadata.get("distance_matrix")
    elif caps.matrix_distances:
        context["matrices_omitted_from_prompt"] = True
    return context


def agent_for_fault(family: str | None) -> str:
    if not family:
        return "architect"
    return _FAULT_AGENT.get(family, "architect")


def load_family_instance(family: str, instance_id: str, *, root: Path | None = None) -> tuple[ProblemSpecV2, Path]:
    """Return the parsed spec and the benchmark file. The file is not modified."""
    spec_row = next((row for row in DATASET_SPECS if row.family_id == family), None)
    loader = _loader_for(family)
    if spec_row is None or loader is None:
        raise FileNotFoundError(f"unknown family {family}")
    folder = (root or DATASET_ROOT) / spec_row.folder_name
    matches = [path for path in _match_instances(folder, spec_row.instance_glob) if path.stem == instance_id]
    if not matches:
        raise FileNotFoundError(f"{family} instance {instance_id} was not found under {folder}")
    path = matches[0]
    spec = loader(path)
    return spec, path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def customer_ids(spec: ProblemSpecV2) -> list[str]:
    if spec.capabilities.pickup_delivery and spec.requests:
        out: list[str] = []
        for request in spec.requests:
            out.extend([request.pickup_id, request.delivery_id])
        return out
    return [node.id for node in spec.nodes if node.kind == "customer"]


def summarize_instance(spec: ProblemSpecV2, *, customer_limit: int = 40) -> dict[str, Any]:
    """Compact description for an agent prompt. It does not include a solution."""
    customers = customer_ids(spec)
    shown = customers[:customer_limit]
    nodes = []
    wanted = set(shown) | set(spec.depot_ids) | {node.id for node in spec.nodes if node.kind == "station"}
    for node in spec.nodes:
        if node.id not in wanted and node.kind == "customer":
            continue
        if node.kind == "customer" and node.id not in shown:
            continue
        nodes.append(
            {
                "id": node.id,
                "kind": node.kind,
                "x": node.x,
                "y": node.y,
                "demand": node.demand,
                "ready_time": node.ready_time,
                "due_time": node.due_time,
                "service_time": node.service_time,
                "recharging_rate": node.recharging_rate,
                "charge_technologies": list(node.charge_technologies),
            }
        )
    vehicles = [
        {
            "type_id": vehicle.type_id,
            "capacity": vehicle.capacity,
            "battery_capacity": vehicle.battery_capacity,
            "consumption_rate": vehicle.consumption_rate,
            "velocity": vehicle.velocity,
            "fixed_cost": vehicle.fixed_cost,
            "variable_cost": vehicle.variable_cost,
            "is_electric": vehicle.is_electric,
            "is_conventional": vehicle.is_conventional,
            "is_hybrid": vehicle.is_hybrid,
        }
        for vehicle in spec.vehicle_types
    ]
    caps = spec.capabilities
    payload = {
        "instance_id": spec.instance_id,
        "family": spec.family,
        "native_objective": native_objective(spec.family),
        "depot_ids": list(spec.depot_ids),
        "customer_ids": customers,
        "customers_omitted_from_prompt": max(0, len(customers) - len(shown)),
        "capabilities": {
            "time_windows": caps.time_windows,
            "capacity": caps.capacity,
            "battery": caps.battery,
            "full_recharge": caps.full_recharge,
            "partial_recharge": caps.partial_recharge,
            "nonlinear_charging": caps.nonlinear_charging,
            "multiple_charge_technologies": caps.multiple_charge_technologies,
            "pickup_delivery": caps.pickup_delivery,
            "heterogeneous_fleet": caps.heterogeneous_fleet,
        },
        "vehicles": vehicles,
        "fleet_availability": dict(spec.fleet_availability),
        "requests": [
            {
                "request_id": request.request_id,
                "pickup_id": request.pickup_id,
                "delivery_id": request.delivery_id,
                "demand": request.demand,
            }
            for request in spec.requests
        ],
        "nodes": nodes,
    }
    if len(customers) <= 15 and not spec.capabilities.matrix_distances:
        payload["travel"] = _travel_notes(spec, customers)
    payload["problem"] = problem_context(spec, include_matrices=len(spec.nodes) <= 20)
    return payload


def _travel_notes(spec: ProblemSpecV2, customers: list[str]) -> dict[str, Any]:
    """Distances and earliest depot arrivals. This does not choose a route."""
    depot = spec.node_map[spec.depot_ids[0]]

    def distance(left: str, right: str) -> float:
        a = spec.node_map[left]
        b = spec.node_map[right]
        return float(((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5)

    return {
        "customer_from_depot": [
            {
                "id": node_id,
                "distance_from_depot": round(distance(depot.id, node_id), 2),
                "round_trip_distance": round(2 * distance(depot.id, node_id), 2),
                "ready_time": spec.node_map[node_id].ready_time,
                "due_time": spec.node_map[node_id].due_time,
                "service_time": spec.node_map[node_id].service_time,
            }
            for node_id in customers
        ],
        "between_customers": [
            {"from": left, "to": right, "distance": round(distance(left, right), 2)}
            for index, left in enumerate(customers)
            for right in customers[index + 1 :]
        ],
    }


def spec_payload(spec: ProblemSpecV2) -> dict[str, Any]:
    """JSON a generated solver may read. It is data, not a Python object."""
    summary = summarize_instance(spec, customer_limit=10**9)
    summary["nodes"] = [
        {
            "id": node.id,
            "kind": node.kind,
            "x": node.x,
            "y": node.y,
            "demand": node.demand,
            "ready_time": node.ready_time,
            "due_time": node.due_time,
            "service_time": node.service_time,
            "recharging_rate": node.recharging_rate,
            "charge_technologies": list(node.charge_technologies),
        }
        for node in spec.nodes
    ]
    summary["problem"] = problem_context(spec, include_matrices=True)
    return summary
