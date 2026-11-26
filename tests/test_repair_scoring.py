"""Classical repair must distinguish total-route vs marginal-distance ranking."""

from __future__ import annotations

import random

from evrptw_autolab.backbone.alns import classical_repair_rank_score, repair_greedy
from evrptw_autolab.backbone.decision_features import insertion_features_v4
from evrptw_autolab.backbone.route_screen import screen_repair_route
from evrptw_autolab.backbone.util import make_customer_stop, vehicle_for_route
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    RouteStopV2,
    SolutionV2,
    VehicleTypeV2,
)


def _spec() -> ProblemSpecV2:
    """Two-route geometry where total-route and marginal criteria disagree.

    Route A (long): D-A50-A60-A70-D. Inserting P near A50/A60 has tiny delta but large total.
    Route B (short): D-B10-D. Inserting P has large delta but smaller post-insertion total.
    """
    return ProblemSpecV2(
        instance_id="repair_scoring_disagreement",
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
            NodeV2("A50", "customer", 50.0, 0.0, demand=1.0, due_time=10_000.0),
            NodeV2("A60", "customer", 60.0, 0.0, demand=1.0, due_time=10_000.0),
            NodeV2("A70", "customer", 70.0, 0.0, demand=1.0, due_time=10_000.0),
            NodeV2("B10", "customer", 0.0, 10.0, demand=1.0, due_time=10_000.0),
            NodeV2("P", "customer", 55.0, 1.0, demand=1.0, due_time=10_000.0),
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


def _partial() -> SolutionV2:
    return SolutionV2(
        routes=[
            [
                RouteStopV2("D", "EV", "depot"),
                RouteStopV2("A50", "EV", "visit"),
                RouteStopV2("A60", "EV", "visit"),
                RouteStopV2("A70", "EV", "visit"),
                RouteStopV2("D", "EV", "depot"),
            ],
            [
                RouteStopV2("D", "EV", "depot"),
                RouteStopV2("B10", "EV", "visit"),
                RouteStopV2("D", "EV", "depot"),
            ],
        ],
        vehicle_assignments=["EV", "EV"],
    )


def _best_labels(spec: ProblemSpecV2, solution: SolutionV2) -> tuple[str, str]:
    """Return (label minimizing total route distance, label minimizing delta)."""
    node_id = "P"
    best_total: tuple[float, str] | None = None
    best_delta: tuple[float, str] | None = None
    for r_idx, route in enumerate(solution.routes):
        vehicle = vehicle_for_route(spec, solution, r_idx)
        for pos in range(1, len(route)):
            trial = list(route)
            trial.insert(pos, make_customer_stop(node_id, spec))
            ok, total = screen_repair_route(spec, trial, vehicle, allow_battery_debt=True)
            if not ok:
                continue
            features = insertion_features_v4(spec, route, pos, node_id, vehicle)
            label = f"r{r_idx}:{pos}"
            total_key = (float(total), label)
            delta_key = (float(features["delta_distance"]), label)
            if best_total is None or total_key < best_total:
                best_total = total_key
            if best_delta is None or delta_key < best_delta:
                best_delta = delta_key
    assert best_total is not None and best_delta is not None
    assert best_total[1] != best_delta[1], "geometry must make B0 and B1 disagree"
    return best_total[1], best_delta[1]


def _route_of_customer(solution: SolutionV2, node_id: str) -> int:
    for idx, route in enumerate(solution.routes):
        if any(stop.node_id == node_id for stop in route):
            return idx
    raise AssertionError(f"{node_id} not inserted")


def test_rank_helpers_separate_total_and_marginal() -> None:
    assert classical_repair_rank_score(
        "total_route_distance", total_route_distance=58.0, delta_distance=18.0
    ) == 58.0
    assert classical_repair_rank_score(
        "marginal_delta_distance", total_route_distance=58.0, delta_distance=18.0
    ) == 18.0
    assert classical_repair_rank_score(
        "marginal_fleet_aware",
        total_route_distance=58.0,
        delta_distance=18.0,
        route_customer_count=3.0,
    ) == 18.0 - 0.03


def test_b0_and_b1_disagree_on_illustrative_insertion() -> None:
    spec = _spec()
    start = _partial()
    total_label, delta_label = _best_labels(spec, start)
    assert total_label.startswith("r1"), "B0 should prefer the short route"
    assert delta_label.startswith("r0"), "B1 should prefer the long route"

    b0 = repair_greedy(
        spec,
        start,
        [("P",)],
        random.Random(0),
        policy=None,
        optimize_partial_charges=False,
        repair_scoring_mode="total_route_distance",
    )
    b1 = repair_greedy(
        spec,
        start,
        [("P",)],
        random.Random(0),
        policy=None,
        optimize_partial_charges=False,
        repair_scoring_mode="marginal_delta_distance",
    )
    assert _route_of_customer(b0, "P") == 1
    assert _route_of_customer(b1, "P") == 0
    assert b0.metadata.get("repair_scoring_mode") == "total_route_distance"
    assert b1.metadata.get("repair_scoring_mode") == "marginal_delta_distance"
