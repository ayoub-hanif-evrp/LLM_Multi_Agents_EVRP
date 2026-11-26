"""Related/Shaw destroy removes a coherent neighborhood around a seed."""

from __future__ import annotations

import random

from evrptw_autolab.backbone.alns import destroy_related
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    RouteStopV2,
    SolutionV2,
    VehicleTypeV2,
)


def _spec() -> ProblemSpecV2:
    return ProblemSpecV2(
        instance_id="related_destroy",
        family="schneider",
        capabilities=CapabilityFlags(
            time_windows=True,
            capacity=True,
            battery=True,
            full_recharge=True,
            euclidean_distances=True,
        ),
        nodes=(
            NodeV2("D", "depot", 0.0, 0.0, due_time=10_000.0),
            NodeV2("A", "customer", 1.0, 0.0, demand=1.0, due_time=100.0),
            NodeV2("B", "customer", 1.5, 0.2, demand=1.0, due_time=110.0),
            NodeV2("C", "customer", 50.0, 50.0, demand=1.0, due_time=900.0),
            NodeV2("E", "customer", 51.0, 49.0, demand=1.0, due_time=910.0),
        ),
        vehicle_types=(
            VehicleTypeV2(
                "EV",
                capacity=100.0,
                battery_capacity=100_000.0,
                consumption_rate=0.01,
                velocity=1.0,
                metadata={"inverse_refuel_rate": 1.0},
            ),
        ),
        depot_ids=("D",),
        objective="minimize_vehicles_then_distance",
    )


def test_related_destroy_prefers_nearby_pair() -> None:
    spec = _spec()
    sol = SolutionV2(
        routes=[
            [
                RouteStopV2("D", "EV", "depot"),
                RouteStopV2("A", "EV", "visit"),
                RouteStopV2("B", "EV", "visit"),
                RouteStopV2("D", "EV", "depot"),
            ],
            [
                RouteStopV2("D", "EV", "depot"),
                RouteStopV2("C", "EV", "visit"),
                RouteStopV2("E", "EV", "visit"),
                RouteStopV2("D", "EV", "depot"),
            ],
        ],
        vehicle_assignments=["EV", "EV"],
    )
    # Force deterministic seed selection toward cluster A/B by trying several rng seeds.
    nearby_hits = 0
    for seed in range(20):
        _destroyed, removed = destroy_related(spec, sol, random.Random(seed), k=2)
        ids = {n for unit in removed for n in unit}
        if ids <= {"A", "B"} or ids <= {"C", "E"}:
            nearby_hits += 1
    assert nearby_hits >= 10, "related destroy should usually keep removals within one cluster"
