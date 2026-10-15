"""Adapter: legacy Schneider EVRPTWInstance → ProblemSpecV2."""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.problem.schneider import load_instance
from evrptw_autolab.problem.v2.types import (
    NodeV2,
    ProblemSpecV2,
    VehicleTypeV2,
    schneider_capabilities,
)


def load_schneider_v2(path: Path | str) -> ProblemSpecV2:
    legacy = load_instance(Path(path))
    nodes = tuple(
        NodeV2(
            id=n.id,
            kind=n.kind,
            x=n.x,
            y=n.y,
            demand=n.demand,
            ready_time=n.ready_time,
            due_time=n.due_time,
            service_time=n.service_time,
        )
        for n in legacy.nodes
    )
    vehicle = VehicleTypeV2(
        type_id="EV",
        capacity=legacy.vehicle.capacity,
        battery_capacity=legacy.vehicle.battery_capacity,
        consumption_rate=legacy.vehicle.consumption_rate,
        velocity=legacy.vehicle.velocity,
        is_electric=True,
        metadata={"inverse_refuel_rate": legacy.vehicle.inverse_refuel_rate},
    )
    return ProblemSpecV2(
        instance_id=legacy.instance_id,
        family="schneider",
        capabilities=schneider_capabilities(),
        nodes=nodes,
        vehicle_types=(vehicle,),
        depot_ids=(legacy.depot_id,),
        fleet_availability={"EV": 10**9},
        objective="minimize_vehicles_then_distance",
        metadata={
            **dict(legacy.metadata),
            "legacy_adapter": True,
        },
    )
