"""A selected operator can change an insertion. A worse one does not replace the incumbent."""

import random

import pytest
from tests.conftest import DATA_ROOT

from evrptw_autolab.backbone.alns import destroy_random, repair_greedy
from evrptw_autolab.backbone.construct import construct_greedy
from evrptw_autolab.backbone.solver import ClassicalSolver
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.evaluation.fidelity import partition_of
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.problem.schneider import load_instance
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    RouteStopV2,
    SolutionV2,
    VehicleTypeV2,
)
from evrptw_autolab.transfer.context_features import search_context


def _spec() -> ProblemSpecV2:
    return ProblemSpecV2(
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


def _start() -> SolutionV2:
    return SolutionV2(
        routes=[
            [
                RouteStopV2("D", vehicle_type_id="EV", event="depot"),
                RouteStopV2("A", vehicle_type_id="EV", event="visit"),
                RouteStopV2("B", vehicle_type_id="EV", event="visit"),
                RouteStopV2("D", vehicle_type_id="EV", event="depot"),
            ]
        ],
        vehicle_assignments=["EV"],
    )


def _operator(**overrides: object) -> OperatorSpec:
    payload: dict[str, object] = {
        "operator_id": "long_detour",
        "version": "1",
        "source_agent": "test",
        "description": "Prefer the longer insertion detour.",
        "operator_family": "repair",
        "implementation_reference": "repair_greedy",
        "required_capabilities": ["time_windows"],
        "applicability_rule": "1",
        "candidate_scoring_policy": "-1 * delta_distance",
        "mine_counterexamples": True,
        "fallback_operator": "classical_default",
    }
    payload.update(overrides)
    return OperatorSpec.model_validate(payload)


def test_context_features_omit_the_instance_identity() -> None:
    features = search_context(_spec(), _start())
    assert "instance_id" not in features
    assert "filename" not in features
    assert features["customer_count"] == 3.0
    assert features["route_utilization"] < 0.9


def test_inverted_distance_changes_the_repair_and_records_the_regression() -> None:
    spec = _spec()
    chosen = repair_greedy(spec, _start(), [("C",)], random.Random(1), _operator())
    decision = chosen.metadata["search_decision"]
    assert decision["action"] == "apply"
    assert decision["changed"] is True
    assert chosen.metadata["counterexamples"][0]["counterexample_type"] == "objective_regression"
    classical = repair_greedy(spec, _start(), [("C",)], random.Random(1), None)
    assert evaluate(spec, classical).feasible
    assert evaluate(spec, chosen).feasible
    assert evaluate(spec, chosen).objective_key > evaluate(spec, classical).objective_key
    solver = ClassicalSolver(seed=1, time_limit_s=1.0, use_alns=False, hard_timeout=False)
    box: dict = {}
    solver._publish(box, spec, classical)
    solver._publish(box, spec, chosen)
    assert evaluate(spec, box["incumbent"]).objective_key == evaluate(spec, classical).objective_key


def test_low_utilization_keeps_the_classical_insertion() -> None:
    spec = _spec()
    operator = _operator(applicability_rule="route_utilization - 0.9")
    chosen = repair_greedy(spec, _start(), [("C",)], random.Random(1), operator)
    classical = repair_greedy(spec, _start(), [("C",)], random.Random(1), None)
    assert chosen.metadata["search_decision"]["action"] == "classical_default"
    assert chosen.metadata["search_decision"]["changed"] is False
    assert "counterexamples" not in chosen.metadata
    assert [stop.node_id for stop in chosen.routes[0]] == [stop.node_id for stop in classical.routes[0]]


def test_missing_capability_does_not_apply_the_harmful_score() -> None:
    chosen = repair_greedy(
        _spec(),
        _start(),
        [("C",)],
        random.Random(1),
        _operator(required_capabilities=["pickup_delivery"]),
    )
    assert chosen.metadata["search_decision"]["action"] == "classical_default"
    assert chosen.metadata["search_decision"]["changed"] is False


def test_held_out_partition_refuses_counterexample_mining() -> None:
    with pytest.raises(RuntimeError, match="refused"):
        repair_greedy(_spec(), _start(), [("C",)], random.Random(1), _operator(), partition="heldout")


def test_development_schneider_repair_records_the_controller_action() -> None:
    legacy = load_instance(DATA_ROOT / "c101C5.txt")
    assert partition_of(legacy) == "discovery"
    spec = load_schneider_v2(DATA_ROOT / "c101C5.txt")
    built = construct_greedy(spec, random.Random(1))
    destroyed, removed = destroy_random(spec, built, random.Random(1), 1)
    assert removed
    operator = _operator(applicability_rule="1")
    repaired = repair_greedy(spec, destroyed, removed, random.Random(1), operator, partition="discovery")
    assert repaired.metadata["search_decision"]["action"] == "apply"
    assert repaired.metadata["search_decision"]["operator_id"] == "long_detour"
