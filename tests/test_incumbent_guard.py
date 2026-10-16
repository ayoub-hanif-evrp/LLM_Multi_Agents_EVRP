"""Feasible incumbents survive shorter energy-infeasible candidates."""
from __future__ import annotations

from evrptw_autolab.backbone.solver import ClassicalSolver
from evrptw_autolab.backbone.util import evaluate
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
        instance_id="incumbent_guard",
        family="schneider",
        capabilities=CapabilityFlags(
            battery=True,
            full_recharge=True,
            time_windows=True,
            euclidean_distances=True,
        ),
        nodes=(
            NodeV2("D", "depot", 0, 0, due_time=10_000),
            NodeV2("C", "customer", 4, 0, demand=1, due_time=10_000),
            NodeV2("S", "station", 2, 2, due_time=10_000),
        ),
        vehicle_types=(
            VehicleTypeV2(
                "EV",
                capacity=10,
                battery_capacity=7,
                consumption_rate=1,
                velocity=1,
                metadata={"inverse_refuel_rate": 1.0},
            ),
        ),
        depot_ids=("D",),
        objective="minimize_vehicles_then_distance",
    )


def test_publish_keeps_feasible_route_over_shorter_battery_failure() -> None:
    spec = _spec()
    feasible = SolutionV2(
        routes=[
            [
                RouteStopV2("D", vehicle_type_id="EV", event="depot"),
                RouteStopV2("S", vehicle_type_id="EV", event="charge"),
                RouteStopV2("C", vehicle_type_id="EV", event="visit"),
                RouteStopV2("D", vehicle_type_id="EV", event="depot"),
            ]
        ],
        vehicle_assignments=["EV"],
    )
    shorter_infeasible = SolutionV2(
        routes=[
            [
                RouteStopV2("D", vehicle_type_id="EV", event="depot"),
                RouteStopV2("C", vehicle_type_id="EV", event="visit"),
                RouteStopV2("D", vehicle_type_id="EV", event="depot"),
            ]
        ],
        vehicle_assignments=["EV"],
    )
    feasible_report = evaluate(spec, feasible)
    infeasible_report = evaluate(spec, shorter_infeasible)
    assert feasible_report.feasible
    assert not infeasible_report.feasible
    assert infeasible_report.total_distance < feasible_report.total_distance

    solver = ClassicalSolver(seed=1, time_limit_s=1.0, use_alns=False, hard_timeout=False)
    box: dict = {}
    solver._publish(box, spec, feasible)
    solver._publish(box, spec, shorter_infeasible)
    kept = box["incumbent"]
    kept_report = evaluate(spec, kept)
    assert kept_report.feasible
    assert [stop.node_id for stop in kept.routes[0]] == ["D", "S", "C", "D"]
