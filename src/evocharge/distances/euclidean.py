from __future__ import annotations

import math

from evocharge.domain.arc import ArcMetrics
from evocharge.domain.instance import Instance
from evocharge.domain.node import Node


def euclidean_distance(a: Node, b: Node) -> float:
    if a.coordinates is None or b.coordinates is None:
        raise ValueError(f"Missing coordinates for arc {a.id}->{b.id}")
    dx = a.coordinates[0] - b.coordinates[0]
    dy = a.coordinates[1] - b.coordinates[1]
    return math.hypot(dx, dy)


def arc_metrics(instance: Instance, from_id: str, to_id: str) -> ArcMetrics:
    origin = instance.nodes[from_id]
    dest = instance.nodes[to_id]
    distance = euclidean_distance(origin, dest)
    velocity = instance.vehicle.velocity
    if velocity <= 0.0:
        raise ValueError("Vehicle velocity must be positive")
    travel_time = distance / velocity
    energy = distance * instance.vehicle.consumption_rate
    reachable = math.isfinite(distance) and math.isfinite(travel_time) and math.isfinite(energy)
    return ArcMetrics(
        distance=distance,
        travel_time=travel_time,
        energy=energy,
        reachable=reachable,
    )
