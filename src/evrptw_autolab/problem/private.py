"""Private anti-memorization EVRPTW instances. Evaluation-only; never shown during discovery."""
from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path
from random import Random

from evrptw_autolab.problem.types import EVRPTWInstance, Node, VehicleSpec

PRIVATE_PREFIX = "vfpriv"


def _smoke_solomon(n_customers: int) -> str:
    lines = [
        "StringID   Type       x          y          demand     ReadyTime  DueDate    ServiceTime",
        "D0         d          0.0        0.0        0.0        0.0        1000.0     0.0",
        "S0         f          0.5        0.0        0.0        0.0        1000.0     0.0",
    ]
    for i in range(1, n_customers + 1):
        lines.append(
            f"C{i:<9} c          {float(i):<10} 0.0        1.0        0.0        1000.0     0.0"
        )
    lines.extend(
        [
            "",
            "Q Vehicle fuel tank capacity /100.0/",
            "C Vehicle load capacity /100.0/",
            "r fuel consumption rate /1.0/",
            "g inverse refueling rate /1.0/",
            "v average Velocity /1.0/",
        ]
    )
    return "\n".join(lines) + "\n"


def smoke_instance(n_customers: int = 1) -> EVRPTWInstance:
    """Tiny synthetic instance for executable-smoke and curriculum. Not a Schneider case."""
    if n_customers < 1:
        raise ValueError("n_customers must be >= 1")
    from evrptw_autolab.problem.schneider import load_instance

    root = Path(tempfile.gettempdir()) / "evrptw_autolab_smoke"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"smoke_c{n_customers}.txt"
    text = _smoke_solomon(n_customers)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    instance = load_instance(path)
    metadata = dict(instance.metadata)
    metadata.update({"family": "SMOKE", "scale": "smoke", "private": True, "lab_smoke": True})
    return EVRPTWInstance(
        instance_id=f"smoke_c{n_customers}",
        nodes=instance.nodes,
        vehicle=instance.vehicle,
        depot_id=instance.depot_id,
        metadata=metadata,
    )


def perturb_instance(
    instance: EVRPTWInstance,
    seed: int,
    *,
    location_scale: float = 0.04,
    window_scale: float = 0.03,
    demand_scale: float = 0.05,
    battery_scale: float = 0.02,
) -> EVRPTWInstance:
    """Controlled perturbation of a public instance. Same mathematical contract, hidden geometry."""
    rng = Random(seed)
    nodes: list[Node] = []
    for node in instance.nodes:
        if node.kind == "depot":
            nodes.append(node)
            continue
        dx = rng.uniform(-location_scale, location_scale) * max(1.0, abs(node.x))
        dy = rng.uniform(-location_scale, location_scale) * max(1.0, abs(node.y))
        ready = max(0.0, node.ready_time * (1.0 + rng.uniform(-window_scale, window_scale)))
        span = max(1.0, node.due_time - node.ready_time)
        due = ready + span * (1.0 + rng.uniform(-window_scale, window_scale))
        demand = node.demand
        if node.kind == "customer" and demand > 0:
            demand = max(1.0, demand * (1.0 + rng.uniform(-demand_scale, demand_scale)))
        nodes.append(
            replace(
                node,
                x=node.x + dx,
                y=node.y + dy,
                ready_time=ready,
                due_time=due,
                demand=demand,
            )
        )
    factor = 1.0 + rng.uniform(-battery_scale, battery_scale)
    vehicle = VehicleSpec(
        capacity=instance.vehicle.capacity,
        battery_capacity=instance.vehicle.battery_capacity * factor,
        consumption_rate=instance.vehicle.consumption_rate,
        velocity=instance.vehicle.velocity,
        inverse_refuel_rate=instance.vehicle.inverse_refuel_rate,
        initial_soc=None,
    )
    metadata = dict(instance.metadata)
    metadata.update(
        {
            "private": True,
            "private_seed": seed,
            "source_instance_id": instance.instance_id,
            # Materialized by sandbox when None; keep None so agents never see a public path.
            "source_path": None,
        }
    )
    return EVRPTWInstance(
        instance_id=f"{PRIVATE_PREFIX}_{seed}_{instance.instance_id}",
        nodes=tuple(nodes),
        vehicle=vehicle,
        depot_id=instance.depot_id,
        metadata=metadata,
    )


def private_set(instances: list[EVRPTWInstance], seed: int, *, n: int = 8) -> list[EVRPTWInstance]:
    """Build a hidden evaluation set from public templates. Agents never see these ids."""
    templates = [i for i in instances if len(i.customer_ids) in {5, 10, 15}]
    templates.sort(key=lambda i: i.instance_id)
    if not templates:
        raise ValueError("private_set needs small public templates")
    rng = Random(seed)
    chosen = templates[:n] if len(templates) <= n else [templates[i] for i in rng.sample(range(len(templates)), n)]
    return [perturb_instance(instance, seed + index) for index, instance in enumerate(chosen)]
