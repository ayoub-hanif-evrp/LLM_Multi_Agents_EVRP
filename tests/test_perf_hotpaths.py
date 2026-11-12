"""Regression tests for high-frequency solver hot-path optimizations."""

from __future__ import annotations

import pickle
import random
from pathlib import Path

from evrptw_autolab.backbone.alns import repair_greedy
from evrptw_autolab.backbone.route_screen import screen_repair_route
from evrptw_autolab.backbone.util import clone_solution
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    RouteStopV2,
    SolutionV2,
    VehicleTypeV2,
)


def test_node_map_is_cached_and_survives_pickle() -> None:
    spec = ProblemSpecV2(
        instance_id="n",
        family="schneider",
        capabilities=CapabilityFlags(time_windows=True),
        nodes=(NodeV2("D", "depot", 0.0, 0.0), NodeV2("A", "customer", 1.0, 0.0, demand=1.0)),
        vehicle_types=(VehicleTypeV2("EV", capacity=10.0, battery_capacity=100.0, consumption_rate=0.1, velocity=1.0),),
        depot_ids=("D",),
    )
    first = spec.node_map
    second = spec.node_map
    assert first is second
    restored = pickle.loads(pickle.dumps(spec))
    assert restored.node_map["A"].id == "A"
    assert restored.node_map is restored._node_map


def test_clone_solution_shares_frozen_stops_but_not_route_lists() -> None:
    stop = RouteStopV2("A", event="visit")
    original = SolutionV2(routes=[[stop]], vehicle_assignments=["EV"], metadata={"x": 1})
    cloned = clone_solution(original)
    assert cloned.routes[0][0] is original.routes[0][0]
    cloned.routes[0].append(RouteStopV2("B", event="visit"))
    assert len(original.routes[0]) == 1
    cloned.metadata["x"] = 2
    assert original.metadata["x"] == 1


def test_repair_screen_allows_temporary_battery_debt() -> None:
    spec = ProblemSpecV2(
        instance_id="debt",
        family="schneider",
        capabilities=CapabilityFlags(
            time_windows=True, capacity=True, battery=True, full_recharge=True, euclidean_distances=True
        ),
        nodes=(
            NodeV2("D0", "depot", 0.0, 0.0, due_time=1000.0),
            NodeV2("C1", "customer", 40.0, 0.0, demand=1.0, due_time=1000.0, service_time=10.0),
            NodeV2("S1", "station", 20.0, 0.0, due_time=1000.0),
        ),
        vehicle_types=(
            VehicleTypeV2(
                "EV",
                capacity=100.0,
                battery_capacity=30.0,
                consumption_rate=1.0,
                velocity=1.0,
                metadata={"inverse_refuel_rate": 1.0},
            ),
        ),
        depot_ids=("D0",),
    )
    vehicle = spec.vehicle_types[0]
    route = [
        RouteStopV2("D0", event="depot"),
        RouteStopV2("C1", event="visit"),
        RouteStopV2("D0", event="depot"),
    ]
    ok_soft, _ = screen_repair_route(spec, route, vehicle, allow_battery_debt=True)
    ok_hard, _ = screen_repair_route(spec, route, vehicle, allow_battery_debt=False)
    assert ok_soft is True
    assert ok_hard is False


def test_route_local_repair_inserts_without_raising() -> None:
    root = Path(__file__).resolve().parents[1]
    spec = load_schneider_v2(root / "dataset" / "schneider" / "raw_instances" / "c101C5.txt")
    start = SolutionV2(
        routes=[
            [
                RouteStopV2(spec.depot_ids[0], event="depot"),
                RouteStopV2(spec.depot_ids[0], event="depot"),
            ]
        ],
        vehicle_assignments=[spec.vehicle_types[0].type_id],
    )
    customers = [node.id for node in spec.nodes if node.kind == "customer"][:3]
    repaired = repair_greedy(
        spec,
        start,
        [(cid,) for cid in customers],
        random.Random(1),
        partition="development",
        optimize_partial_charges=False,
    )
    assert repaired.routes
    assert len(repaired.routes[0]) >= 3
