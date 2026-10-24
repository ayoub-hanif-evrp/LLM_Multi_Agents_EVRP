"""A policy must change a real removal or a real new-route choice."""
from __future__ import annotations

import random

from evrptw_autolab.backbone.alns import destroy_worst
from evrptw_autolab.backbone.construct import insert_customer_fast
from evrptw_autolab.components.expressions import default_sources, wrap_expression
from evrptw_autolab.components.loader import load_bundle
from evrptw_autolab.problem.v2.features import FEATURE_SCHEMA_V3, FEATURE_SCHEMA_VERSION
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
        instance_id="decision_micro",
        family="hiermann",
        capabilities=CapabilityFlags(
            heterogeneous_fleet=True,
            capacity=True,
            euclidean_distances=True,
        ),
        nodes=(
            NodeV2("D", "depot", 0, 0, due_time=1000),
            NodeV2("A", "customer", 1, 0, demand=1, due_time=10),
            NodeV2("B", "customer", 30, 0, demand=1, due_time=1000),
        ),
        vehicle_types=(
            VehicleTypeV2(
                "ICE",
                capacity=10,
                is_electric=False,
                is_conventional=True,
                velocity=1,
                fixed_cost=100,
            ),
        ),
        depot_ids=("D",),
        fleet_availability={"ICE": 2},
    )


def _two_routes(spec: ProblemSpecV2) -> SolutionV2:
    return SolutionV2(
        routes=[
            [
                RouteStopV2("D", "ICE", "depot"),
                RouteStopV2("A", "ICE", "visit"),
                RouteStopV2("D", "ICE", "depot"),
            ],
            [
                RouteStopV2("D", "ICE", "depot"),
                RouteStopV2("B", "ICE", "visit"),
                RouteStopV2("D", "ICE", "depot"),
            ],
        ],
        vehicle_assignments=["ICE", "ICE"],
    )


def _bundle(kind: str, expression: str):
    sources = default_sources(FEATURE_SCHEMA_V3)
    sources[kind] = wrap_expression(kind, expression, FEATURE_SCHEMA_V3)
    bundle, errors = load_bundle(sources, feature_schema=FEATURE_SCHEMA_V3)
    assert errors == []
    return bundle


def test_default_removal_is_unchanged_by_the_new_distance_feature() -> None:
    spec = _spec()
    solution = _two_routes(spec)
    baseline, _errors = load_bundle(default_sources(FEATURE_SCHEMA_VERSION))
    _destroyed, removed = destroy_worst(spec, solution, random.Random(0), 1, policy=baseline)
    assert removed == [("B",)]


def test_route_distance_changes_which_customer_is_removed() -> None:
    spec = _spec()
    solution = _two_routes(spec)
    bundle = _bundle("removal_priority", "0.0 - own_route_distance")
    _destroyed, removed = destroy_worst(spec, solution, random.Random(0), 1, policy=bundle)
    assert removed == [("A",)]


def test_fixed_cost_policy_can_open_a_route_the_default_keeps_closed() -> None:
    spec = _spec()
    start = SolutionV2(
        routes=[
            [
                RouteStopV2("D", "ICE", "depot"),
                RouteStopV2("A", "ICE", "visit"),
                RouteStopV2("D", "ICE", "depot"),
            ]
        ],
        vehicle_assignments=["ICE"],
    )
    kept = insert_customer_fast(spec, start, "B")
    assert len(kept.routes) == 1
    opened = insert_customer_fast(
        spec,
        start,
        "B",
        policy=_bundle("insertion_score", "delta_distance - new_route_fixed_cost"),
    )
    assert len(opened.routes) == 2
    assert opened.routes[1][1].node_id == "B"
