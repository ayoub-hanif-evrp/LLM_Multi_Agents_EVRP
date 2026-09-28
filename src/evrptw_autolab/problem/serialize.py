"""Serialize EVRPTWInstance to a JSON file the sandbox can reload."""
from __future__ import annotations

import json
from pathlib import Path

from evrptw_autolab.problem.types import EVRPTWInstance, Node, VehicleSpec


def write_instance_json(instance: EVRPTWInstance, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "instance_id": instance.instance_id,
        "depot_id": instance.depot_id,
        "nodes": [
            {
                "id": n.id,
                "kind": n.kind,
                "x": n.x,
                "y": n.y,
                "demand": n.demand,
                "ready_time": n.ready_time,
                "due_time": n.due_time,
                "service_time": n.service_time,
            }
            for n in instance.nodes
        ],
        "vehicle": {
            "capacity": instance.vehicle.capacity,
            "battery_capacity": instance.vehicle.battery_capacity,
            "consumption_rate": instance.vehicle.consumption_rate,
            "velocity": instance.vehicle.velocity,
            "inverse_refuel_rate": instance.vehicle.inverse_refuel_rate,
            "initial_soc": instance.vehicle.initial_soc,
        },
        "metadata": dict(instance.metadata),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_instance_json(path: Path | str) -> EVRPTWInstance:
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    nodes = tuple(
        Node(
            id=str(n["id"]),
            kind=n["kind"],  # type: ignore[arg-type]
            x=float(n["x"]),
            y=float(n["y"]),
            demand=float(n.get("demand") or 0.0),
            ready_time=float(n.get("ready_time") or 0.0),
            due_time=float(n.get("due_time") or 0.0),
            service_time=float(n.get("service_time") or 0.0),
        )
        for n in raw["nodes"]
    )
    v = raw["vehicle"]
    vehicle = VehicleSpec(
        capacity=float(v["capacity"]),
        battery_capacity=float(v["battery_capacity"]),
        consumption_rate=float(v["consumption_rate"]),
        velocity=float(v["velocity"]),
        inverse_refuel_rate=float(v["inverse_refuel_rate"]),
        initial_soc=v.get("initial_soc"),
    )
    metadata = dict(raw.get("metadata") or {})
    metadata["source_path"] = str(path.resolve())
    return EVRPTWInstance(
        instance_id=str(raw["instance_id"]),
        nodes=nodes,
        vehicle=vehicle,
        depot_id=str(raw["depot_id"]),
        metadata=metadata,
    )
