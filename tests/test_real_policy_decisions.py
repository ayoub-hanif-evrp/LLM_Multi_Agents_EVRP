"""Real insertion candidates, not unrelated synthetic rows."""
from __future__ import annotations

import random

from evrptw_autolab.backbone.alns import destroy_worst, repair_greedy
from evrptw_autolab.backbone.construct import insert_customer_fast
from evrptw_autolab.backbone.decision_features import (
    insertion_features_v4,
    marginal_removal_distance,
)
from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import call_scorer, evaluate
from evrptw_autolab.components.expressions import default_sources, wrap_expression
from evrptw_autolab.components.loader import load_bundle
from evrptw_autolab.problem.v2.features import FEATURE_SCHEMA_V4, FEATURE_SCHEMA_VERSION
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    RequestV2,
    RouteStopV2,
    SolutionV2,
    VehicleTypeV2,
)


def _spec() -> ProblemSpecV2:
    return ProblemSpecV2(
        instance_id="repair_micro",
        family="schneider",
        capabilities=CapabilityFlags(capacity=True, euclidean_distances=True, time_windows=True),
        nodes=(
            NodeV2("D", "depot", 0, 0, due_time=1000),
            NodeV2("A", "customer", 5, 0, demand=1, ready_time=0, due_time=100, service_time=0),
            NodeV2("B", "customer", 6, 0, demand=1, ready_time=0, due_time=100, service_time=0),
            NodeV2("C", "customer", 0, 8, demand=1, ready_time=0, due_time=100, service_time=0),
        ),
        vehicle_types=(
            VehicleTypeV2("EV", capacity=20, battery_capacity=500, consumption_rate=0.01, velocity=1, fixed_cost=0),
        ),
        depot_ids=("D",),
    )


def _open_route() -> SolutionV2:
    return SolutionV2(
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


def _positions(spec: ProblemSpecV2) -> list[dict[str, float]]:
    route = _open_route().routes[0]
    vehicle = spec.vehicle_types[0]
    rows = []
    for pos in range(1, len(route)):
        features = insertion_features_v4(spec, route, pos, "C", vehicle)
        features["due_time"] = 100.0
        features["ready_time"] = 0.0
        features["demand"] = 1.0
        features["capacity_slack"] = 17.0
        rows.append(features)
    return rows


def test_constant_due_time_does_not_change_a_real_insertion_ranking() -> None:
    points = _positions(_spec())
    assert len({point["delta_distance"] for point in points}) > 1
    assert len({point["due_time"] for point in points}) == 1
    plain = wrap_expression("insertion_score", "delta_distance")
    nudged = wrap_expression("insertion_score", "delta_distance + 0.01 * due_time")
    left, _ = load_bundle({"insertion_score": plain})
    right, errors = load_bundle({"insertion_score": nudged})
    assert errors == []
    left_scores = [call_scorer(left.insertion_score, point, ()) for point in points]
    right_scores = [call_scorer(right.insertion_score, point, ()) for point in points]
    assert left_scores.index(min(left_scores)) == right_scores.index(min(right_scores))


def test_historical_repair_does_not_call_the_insertion_scorer() -> None:
    spec = _spec()
    bundle, errors = load_bundle(default_sources(FEATURE_SCHEMA_VERSION))
    assert errors == []
    repair_greedy(spec, _open_route(), [("C",)], random.Random(0), policy=bundle)
    assert bundle.call_counts.get("insertion_score", 0) == 0


def test_v4_policy_changes_the_alns_repair_choice_and_stays_feasible() -> None:
    spec = _spec()
    sources = default_sources(FEATURE_SCHEMA_V4)
    sources["insertion_score"] = wrap_expression("insertion_score", "0.0 - delta_distance", FEATURE_SCHEMA_V4)
    bundle, errors = load_bundle(sources, feature_schema=FEATURE_SCHEMA_V4)
    assert errors == []
    classical = repair_greedy(spec, _open_route(), [("C",)], random.Random(0))
    ranked = repair_greedy(spec, _open_route(), [("C",)], random.Random(0), policy=bundle)
    classical_body = [stop.node_id for stop in classical.routes[0]]
    ranked_body = [stop.node_id for stop in ranked.routes[0]]
    assert "C" in classical_body and "C" in ranked_body
    assert classical_body.index("C") != ranked_body.index("C")
    assert bundle.call_counts["insertion_score"] >= 2
    assert bundle.decision_trace[0]["changed_from_objective"] is True
    assert evaluate(spec, ranked).feasible
    assert evaluate(spec, classical).feasible


def test_marginal_removal_differs_for_customers_on_the_same_route() -> None:
    spec = _spec()
    route = _open_route().routes[0]
    near = marginal_removal_distance(spec, route, {"A"})
    far = marginal_removal_distance(spec, route, {"B"})
    assert far > near
    assert near == 0.0


def test_v4_slack_uses_the_candidate_vehicle_not_the_first_type() -> None:
    spec = _spec()
    small = VehicleTypeV2("SMALL", capacity=3, velocity=1, is_electric=False, is_conventional=True)
    large = VehicleTypeV2("LARGE", capacity=30, velocity=1, is_electric=False, is_conventional=True)
    route = _open_route().routes[0]
    small_slack = insertion_features_v4(spec, route, 1, "C", small)["route_load_slack_after_insertion"]
    large_slack = insertion_features_v4(spec, route, 1, "C", large)["route_load_slack_after_insertion"]
    assert small_slack == 0.0
    assert large_slack == 27.0


def test_default_solver_repeat_matches_on_the_micro_instance() -> None:
    spec = _spec()
    kwargs = {"seed": 1, "time_limit_s": 1.0, "alns_iterations": 5}
    first = evaluate(spec, solve_classical(spec, **kwargs))
    second = evaluate(spec, solve_classical(spec, **kwargs))
    assert first.feasible and second.feasible
    assert first.objective_key == second.objective_key


def _fleet_spec() -> ProblemSpecV2:
    return ProblemSpecV2(
        instance_id="two_route_cost",
        family="hiermann",
        capabilities=CapabilityFlags(heterogeneous_fleet=True, capacity=True, euclidean_distances=True),
        nodes=(
            NodeV2("D", "depot", 0, 0, due_time=1000),
            NodeV2("A", "customer", 2, 2, demand=1, due_time=1000),
            NodeV2("B", "customer", -20, 0, demand=1, due_time=1000),
            NodeV2("C", "customer", 2, 0, demand=1, due_time=1000),
        ),
        vehicle_types=(
            VehicleTypeV2(
                "ICE",
                capacity=10,
                is_electric=False,
                is_conventional=True,
                velocity=1,
                fixed_cost=0,
                metadata={"fuel_consumption_rate": 10.0},
            ),
            VehicleTypeV2(
                "BEV",
                capacity=10,
                battery_capacity=100,
                consumption_rate=0.1,
                velocity=1,
                is_electric=True,
                fixed_cost=0,
            ),
        ),
        depot_ids=("D",),
        fleet_availability={"ICE": 1, "BEV": 1},
        metadata={"energy_prices": {"fossil-fuel": 1.0, "electricity": 1.0}, "travel_time_model": "distance_equals_time"},
    )


def _fleet_routes() -> SolutionV2:
    return SolutionV2(
        routes=[
            [RouteStopV2("D", "ICE", "depot"), RouteStopV2("A", "ICE", "visit"), RouteStopV2("D", "ICE", "depot")],
            [RouteStopV2("D", "BEV", "depot"), RouteStopV2("B", "BEV", "visit"), RouteStopV2("D", "BEV", "depot")],
        ],
        vehicle_assignments=["ICE", "BEV"],
    )


def _v4(expression: str):
    sources = default_sources(FEATURE_SCHEMA_V4)
    sources["insertion_score"] = wrap_expression("insertion_score", expression, FEATURE_SCHEMA_V4)
    bundle, errors = load_bundle(sources, feature_schema=FEATURE_SCHEMA_V4)
    assert errors == []
    return bundle


def test_two_routes_make_energy_cost_disagree_with_shortest_detour() -> None:
    spec = _fleet_spec()
    start = _fleet_routes()
    distance = _v4("delta_distance")
    energy = _v4("incremental_energy_cost")
    by_distance = repair_greedy(spec, start, [("C",)], random.Random(0), policy=distance)
    by_energy = repair_greedy(spec, start, [("C",)], random.Random(0), policy=energy)
    distance_route = next(index for index, route in enumerate(by_distance.routes) if any(stop.node_id == "C" for stop in route))
    energy_route = next(index for index, route in enumerate(by_energy.routes) if any(stop.node_id == "C" for stop in route))
    assert distance_route == 0
    assert energy_route == 1
    assert distance.decision_trace[0]["changed_from_objective"] is True
    assert energy.decision_trace[0]["changed_from_objective"] is False
    distance_cost = evaluate(spec, by_distance).objective_key
    energy_cost = evaluate(spec, by_energy).objective_key
    assert energy_cost < distance_cost
    assert evaluate(spec, by_energy).feasible
    points = [
        insertion_features_v4(spec, start.routes[0], 1, "C", spec.vehicle_types[0]),
        insertion_features_v4(spec, start.routes[1], 1, "C", spec.vehicle_types[1]),
    ]
    assert points[0]["incremental_energy_cost"] != points[1]["incremental_energy_cost"]
    assert points[0]["battery_margin"] != points[1]["battery_margin"]


def test_native_energy_repair_prefers_the_cheaper_vehicle() -> None:
    spec = _fleet_spec()
    placed = insert_customer_fast(spec, _fleet_routes(), "C")
    hosts = [
        route[0].vehicle_type_id
        for route in placed.routes
        if any(stop.node_id == "C" for stop in route)
    ]
    assert hosts == ["BEV"]
    assert evaluate(spec, placed).feasible


def test_pickup_delivery_policy_can_change_the_repair_route() -> None:
    spec = ProblemSpecV2(
        instance_id="pair_routes",
        family="goeke",
        capabilities=CapabilityFlags(pickup_delivery=True, capacity=True, euclidean_distances=True),
        nodes=(
            NodeV2("D", "depot", 0, 0, due_time=1000),
            NodeV2("Y", "pickup", 1, 0, demand=1, due_time=1000),
            NodeV2("Z", "delivery", 1, 1, demand=-1, due_time=1000, partner_id="Y"),
            NodeV2("P", "pickup", 8, 0, demand=1, due_time=1000),
            NodeV2("L", "delivery", 8, 1, demand=-1, due_time=1000, partner_id="P"),
        ),
        vehicle_types=(VehicleTypeV2("V", capacity=10, is_electric=False, is_conventional=True, velocity=1),),
        depot_ids=("D",),
        requests=(
            RequestV2("a", "Y", "Z", 1, same_vehicle=True),
            RequestV2("b", "P", "L", 1, same_vehicle=True),
        ),
    )
    start = SolutionV2(
        routes=[
            [RouteStopV2("D", "V", "depot"), RouteStopV2("D", "V", "depot")],
            [
                RouteStopV2("D", "V", "depot"),
                RouteStopV2("Y", "V", "pickup"),
                RouteStopV2("Z", "V", "delivery"),
                RouteStopV2("D", "V", "depot"),
            ],
        ],
        vehicle_assignments=["V", "V"],
    )
    # The empty route has customer count 0. Preferring more customers keeps the pair on the occupied route.
    crowded = _v4("0.0 - route_customer_count")
    repaired = repair_greedy(spec, start, [("P", "L")], random.Random(0), policy=crowded)
    assert evaluate(spec, repaired).feasible
    occupied = repaired.routes[1]
    assert [stop.node_id for stop in occupied].index("P") < [stop.node_id for stop in occupied].index("L")
    assert crowded.decision_trace[0]["stage"] == "alns_repair_pair"


def test_v4_removal_prefers_the_larger_marginal_customer() -> None:
    spec = _spec()
    solution = SolutionV2(
        routes=[
            [
                RouteStopV2("D", "EV", "depot"),
                RouteStopV2("A", "EV", "visit"),
                RouteStopV2("D", "EV", "depot"),
            ],
            [
                RouteStopV2("D", "EV", "depot"),
                RouteStopV2("B", "EV", "visit"),
                RouteStopV2("C", "EV", "visit"),
                RouteStopV2("D", "EV", "depot"),
            ],
        ],
        vehicle_assignments=["EV", "EV"],
    )
    sources = default_sources(FEATURE_SCHEMA_V4)
    bundle, errors = load_bundle(sources, feature_schema=FEATURE_SCHEMA_V4)
    assert errors == []
    _destroyed, removed = destroy_worst(spec, solution, random.Random(0), 1, policy=bundle)
    assert removed[0] != ("A",)
