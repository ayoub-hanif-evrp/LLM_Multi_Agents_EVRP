"""The declared development repair used by the scripted comparison."""

from __future__ import annotations

from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    RouteStopV2,
    SolutionV2,
    VehicleTypeV2,
)


def development_case() -> tuple[ProblemSpecV2, SolutionV2, list[tuple[str, ...]]]:
    """Four-node Schneider repair. This is not a benchmark instance and not a held-out test."""
    spec = ProblemSpecV2(
        instance_id="four_node",
        family="schneider",
        capabilities=CapabilityFlags(
            time_windows=True,
            capacity=True,
            battery=True,
            full_recharge=True,
            euclidean_distances=True,
        ),
        nodes=(
            NodeV2("D", "depot", 0.0, 0.0, due_time=1000.0),
            NodeV2("A", "customer", 5.0, 0.0, demand=1.0, due_time=1000.0),
            NodeV2("B", "customer", 6.0, 0.0, demand=1.0, due_time=1000.0),
            NodeV2("C", "customer", 0.0, 8.0, demand=1.0, due_time=1000.0),
        ),
        vehicle_types=(
            VehicleTypeV2(
                "EV",
                capacity=100.0,
                battery_capacity=1000.0,
                consumption_rate=0.01,
                velocity=1.0,
                metadata={"inverse_refuel_rate": 1.0},
            ),
        ),
        depot_ids=("D",),
        objective="minimize_vehicles_then_distance",
    )
    solution = SolutionV2(
        routes=[
            [
                RouteStopV2("D", "EV", "depot"),
                RouteStopV2("A", "EV", "visit"),
                RouteStopV2("B", "EV", "visit"),
                RouteStopV2("D", "EV", "depot"),
            ]
        ],
        vehicle_assignments=["EV"],
    )
    return spec, solution, [("C",)]
