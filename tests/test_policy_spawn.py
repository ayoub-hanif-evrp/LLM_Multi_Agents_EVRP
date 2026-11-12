"""OperatorSpec must survive hard_timeout spawn and change the same decisions."""

import random

import pytest

from evrptw_autolab.backbone.alns import alns_improve, repair_greedy
from evrptw_autolab.backbone.solver import ClassicalSolver
from evrptw_autolab.discovery.controller import operator_fingerprint
from evrptw_autolab.discovery.policy_codec import decode_policy, encode_policy
from evrptw_autolab.discovery.schemas import OperatorSpec
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
        instance_id="four_node",
        family="schneider",
        capabilities=CapabilityFlags(
            time_windows=True, capacity=True, battery=True, full_recharge=True, euclidean_distances=True
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


def _operator() -> OperatorSpec:
    operator = OperatorSpec(
        operator_id="long_detour",
        version="1",
        source_agent="test",
        description="Prefer the longer detour.",
        operator_family="repair",
        implementation_reference="repair_greedy",
        required_capabilities=["time_windows"],
        applicability_rule="1",
        candidate_scoring_policy="-1 * delta_distance",
        mine_counterexamples=False,
        fallback_operator="classical_default",
    )
    return operator.model_copy(update={"source_hash": operator_fingerprint(operator)})


def test_encode_decode_preserves_operator_hash() -> None:
    operator = _operator()
    restored = decode_policy(encode_policy(operator))
    assert restored is not None
    assert restored.operator_id == operator.operator_id
    assert restored.source_hash == operator.source_hash
    assert restored.candidate_scoring_policy == operator.candidate_scoring_policy


def test_hard_timeout_executes_the_same_operator_as_inprocess() -> None:
    spec = _spec()
    operator = _operator()
    inprocess = ClassicalSolver(
        seed=1,
        time_limit_s=3.0,
        alns_iterations=4,
        use_alns=True,
        hard_timeout=False,
        policy=operator,
        experiment_partition="development",
    ).solve(spec)
    spawned = ClassicalSolver(
        seed=1,
        time_limit_s=3.0,
        alns_iterations=4,
        use_alns=True,
        hard_timeout=True,
        policy=operator,
        experiment_partition="development",
    ).solve(spec)
    assert inprocess.metadata["policy_executed"] is True
    assert spawned.metadata["policy_executed"] is True
    assert spawned.metadata["method_attribution"] == "llm_policy_search"
    assert spawned.metadata["operator_id"] == "long_detour"
    assert spawned.metadata["source_hash"] == operator.source_hash
    assert inprocess.metadata["source_hash"] == spawned.metadata["source_hash"]
    assert inprocess.metadata["experiment_partition"] == "development"
    assert spawned.metadata.get("experiment_partition") == "development"


def test_hard_timeout_without_policy_stays_classical() -> None:
    solution = ClassicalSolver(
        seed=1,
        time_limit_s=1.0,
        use_alns=False,
        hard_timeout=True,
        policy=None,
        experiment_partition="development",
    ).solve(_spec())
    assert solution.metadata["policy_executed"] is False
    assert solution.metadata["method_attribution"] == "classical_baseline"
    assert solution.metadata["changed_decisions"] == 0


def test_hard_timeout_records_same_changed_decisions_as_inprocess() -> None:
    spec = _spec()
    operator = _operator()
    kwargs = dict(
        seed=2,
        time_limit_s=3.0,
        alns_iterations=6,
        use_alns=True,
        policy=operator,
        experiment_partition="development",
    )
    inprocess = ClassicalSolver(hard_timeout=False, **kwargs).solve(spec)
    spawned = ClassicalSolver(hard_timeout=True, **kwargs).solve(spec)
    assert inprocess.metadata["changed_decisions"] == spawned.metadata["changed_decisions"]
    assert inprocess.metadata["selected_move_changed"] == spawned.metadata["selected_move_changed"]
    assert inprocess.metadata["objective_key"] == spawned.metadata["objective_key"]


def test_heldout_partition_refuses_mining_inside_alns() -> None:
    spec = _spec()
    start = SolutionV2(
        routes=[
            [
                RouteStopV2("D", "EV", "depot"),
                RouteStopV2("A", "EV", "visit"),
                RouteStopV2("B", "EV", "visit"),
                RouteStopV2("C", "EV", "visit"),
                RouteStopV2("D", "EV", "depot"),
            ]
        ],
        vehicle_assignments=["EV"],
    )
    operator = _operator().model_copy(update={"mine_counterexamples": True})
    with pytest.raises(RuntimeError, match="refused"):
        alns_improve(
            spec,
            start,
            random.Random(1),
            iterations=1,
            time_limit_s=2.0,
            heavy_local=False,
            policy=operator,
            partition="heldout",
        )


def test_fleet_worsening_move_is_not_sa_accepted() -> None:
    from evrptw_autolab.backbone.alns import _fleet_worsened
    from evrptw_autolab.problem.v2.report import EvaluationReportV2

    current = EvaluationReportV2(feasible=True, objective_key=(1.0, 40.0), vehicles=1)
    worse_fleet = EvaluationReportV2(feasible=True, objective_key=(2.0, 10.0), vehicles=2)
    assert _fleet_worsened(_spec(), worse_fleet, current) is True
    assert _fleet_worsened(_spec(), current, worse_fleet) is False


def test_repair_records_changed_decision_count() -> None:
    spec = _spec()
    start = SolutionV2(
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
    repaired = repair_greedy(spec, start, [("C",)], random.Random(1), _operator(), partition="development")
    assert repaired.metadata["search_decision"]["changed"] is True
    assert repaired.metadata["changed_decisions"] >= 1
    assert repaired.metadata["search_decision"]["source_hash"] == _operator().source_hash
