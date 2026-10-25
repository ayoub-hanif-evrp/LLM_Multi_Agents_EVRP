"""Destroy, charging, fleet, learned applicability, discovery, and the scripted comparison."""

import json
import random

import pytest
from tests.conftest import DATA_ROOT

from evrptw_autolab.backbone.alns import alns_improve, repair_greedy
from evrptw_autolab.backbone.solver import _reassign_vehicles
from evrptw_autolab.backbone.station_filter import rank_station_candidates
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.discovery.controller import CallBudget, admit, run_cycle
from evrptw_autolab.discovery.messages import Hypothesis, validate_hypothesis
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.evaluation.fidelity import partition_of
from evrptw_autolab.llm.registry import FakeBackend
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
from evrptw_autolab.research.compare import (
    evaluate_frozen,
    refuse_heldout_selection,
    run_comparison,
    significance_allowed,
)
from evrptw_autolab.transfer.applicability import ApplicabilityExample, fit_stump


def _four() -> tuple[ProblemSpecV2, SolutionV2]:
    spec = ProblemSpecV2(
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
    return spec, solution


def _operator(**overrides: object) -> OperatorSpec:
    payload: dict[str, object] = {
        "operator_id": "long_detour",
        "version": "1",
        "source_agent": "test",
        "description": "Prefer the longer detour.",
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


def test_destroy_operator_selects_worst_removal() -> None:
    spec, partial = _four()
    full = repair_greedy(spec, partial, [("C",)], random.Random(1), None)
    operator = _operator(
        operator_family="destroy",
        implementation_reference="destroy_worst",
        candidate_scoring_policy="1",
        mine_counterexamples=False,
    )
    improved = alns_improve(
        spec, full, random.Random(1), iterations=1, time_limit_s=5.0, heavy_local=False, policy=operator
    )
    assert improved.metadata["destroy_trace"][0]["name"] == "worst"
    assert improved.metadata["destroy_trace"][0]["action"] == "apply"


def test_charging_operator_can_prefer_the_longer_feasible_station() -> None:
    spec = ProblemSpecV2(
        instance_id="two_stations",
        family="schneider",
        capabilities=CapabilityFlags(battery=True, full_recharge=True, euclidean_distances=True, time_windows=True),
        nodes=(
            NodeV2("D", "depot", 0.0, 0.0, due_time=1000.0),
            NodeV2("C", "customer", 40.0, 0.0, demand=1.0, due_time=1000.0),
            NodeV2("S1", "station", 20.0, 0.0, due_time=1000.0, recharging_rate=1.0),
            NodeV2("S2", "station", 20.0, 8.0, due_time=1000.0, recharging_rate=1.0),
        ),
        vehicle_types=(
            VehicleTypeV2(
                "EV",
                capacity=10.0,
                battery_capacity=30.0,
                consumption_rate=1.0,
                velocity=1.0,
                metadata={"inverse_refuel_rate": 0.1},
            ),
        ),
        depot_ids=("D",),
    )
    vehicle = spec.vehicle_types[0]
    operator = _operator(
        operator_family="charging",
        implementation_reference="rank_station_candidates",
        required_capabilities=["battery"],
        candidate_scoring_policy="-1 * detour",
        mine_counterexamples=False,
    )
    chosen, _ordered = rank_station_candidates(
        spec, "D", "C", vehicle, battery_arrival=30.0, policy=operator
    )
    assert chosen is not None
    assert chosen.station_id == "S2"
    fallback = _operator(
        operator_family="charging",
        implementation_reference="rank_station_candidates",
        required_capabilities=["battery"],
        applicability_rule="0",
        candidate_scoring_policy="-1 * detour",
        mine_counterexamples=False,
    )
    classical, _ordered = rank_station_candidates(
        spec, "D", "C", vehicle, battery_arrival=30.0, policy=fallback
    )
    assert classical is not None
    assert classical.station_id == "S1"


def test_fleet_operator_can_select_a_more_expensive_feasible_vehicle() -> None:
    spec = ProblemSpecV2(
        instance_id="two_types",
        family="hiermann",
        capabilities=CapabilityFlags(
            heterogeneous_fleet=True, conventional_vehicles=True, capacity=True, euclidean_distances=True
        ),
        nodes=(
            NodeV2("D", "depot", 0.0, 0.0, due_time=100.0),
            NodeV2("C", "customer", 1.0, 0.0, demand=1.0, due_time=50.0, service_time=0.0),
        ),
        vehicle_types=(
            VehicleTypeV2(
                "cheap",
                capacity=10.0,
                is_electric=False,
                is_conventional=True,
                velocity=1.0,
                fixed_cost=10.0,
                metadata={"propulsion": "ICEV", "fuel_consumption_rate": 1.0},
            ),
            VehicleTypeV2(
                "costly",
                capacity=10.0,
                is_electric=False,
                is_conventional=True,
                velocity=1.0,
                fixed_cost=50.0,
                metadata={"propulsion": "ICEV", "fuel_consumption_rate": 1.0},
            ),
        ),
        depot_ids=("D",),
        metadata={"travel_time_model": "distance_equals_time", "energy_prices": {"fossil-fuel": 1.0, "electricity": 0.0}},
    )
    solution = SolutionV2(
        routes=[[RouteStopV2("D", "cheap", "depot"), RouteStopV2("C", "cheap", "visit"), RouteStopV2("D", "cheap", "depot")]],
        vehicle_assignments=["cheap"],
    )
    operator = _operator(
        operator_family="fleet",
        implementation_reference="reassign_vehicle",
        required_capabilities=["heterogeneous_fleet"],
        candidate_scoring_policy="-1 * fixed_cost",
    )
    chosen = _reassign_vehicles(spec, solution, policy=operator)
    classical = _reassign_vehicles(spec, solution, policy=None)
    assert chosen.vehicle_assignments == ["costly"]
    assert classical.vehicle_assignments == ["cheap"]
    assert evaluate(spec, chosen).objective_key > evaluate(spec, classical).objective_key
    assert chosen.metadata["counterexamples"][0]["counterexample_type"] == "objective_regression"


def test_stump_learns_when_the_operator_helps_and_refuses_confirmation() -> None:
    stump = fit_stump(
        [
            ApplicabilityExample({"route_utilization": 0.2}, False, "development"),
            ApplicabilityExample({"route_utilization": 0.95}, True, "discovery"),
        ]
    )
    assert stump.predicts_apply({"route_utilization": 0.2}) is False
    assert stump.predicts_apply({"route_utilization": 0.95}) is True
    with pytest.raises(RuntimeError, match="refused"):
        fit_stump([ApplicabilityExample({"route_utilization": 0.95}, True, "confirmation")])


def test_discovery_cycle_revises_the_rule_after_a_counterexample() -> None:
    spec, solution = _four()
    proposal = _operator().model_dump()
    backend = FakeBackend(
        {
            "architect": json.dumps(
                {
                    "hypothesis": "Negative distance weight lengthens the insertion when utilization is low.",
                    "target_bottleneck": "insertion ranking",
                    "affected_capabilities": ["time_windows"],
                    "proposed_operator_id": "long_detour",
                    "expected_useful_conditions": "high route utilization",
                    "expected_failure_conditions": "low route utilization",
                    "measurable_prediction": "the native objective increases on this repair",
                }
            ),
            "routing_specialist": json.dumps(proposal),
            "critic": json.dumps(
                {
                    "what_failed": "the longer detour raised the native objective",
                    "operator_should_change": False,
                    "applicability_should_change": True,
                    "evidence_too_weak": False,
                    "revised_applicability_rule": "route_utilization - 0.9",
                }
            ),
        }
    )
    result = run_cycle(backend, spec, solution, [("C",)], partition="development", budget=CallBudget(4))
    assert result["llm_calls"] == 3
    assert result["roles"] == ["architect", "routing_specialist", "critic"]
    assert result["counterexamples"]
    assert result["operator"]["applicability_rule"] == "route_utilization - 0.9"
    assert result["decision"]["action"] == "classical_default"
    assert result["revised_counterexamples"] == []
    with pytest.raises(RuntimeError, match="budget"):
        run_cycle(backend, spec, solution, [("C",)], partition="development", budget=CallBudget(2))


def test_generic_hypothesis_and_duplicate_operator_are_rejected() -> None:
    with pytest.raises(ValueError, match="generic"):
        validate_hypothesis(
            Hypothesis(
                hypothesis="use better optimization",
                target_bottleneck="search",
                affected_capabilities=["battery"],
                proposed_operator_id="x",
                expected_useful_conditions="none",
                expected_failure_conditions="none",
                measurable_prediction="distance falls",
            )
        )
    seen: set[str] = set()
    operator = _operator()
    admit(operator, seen, _four()[0].capabilities)
    with pytest.raises(ValueError, match="duplicate"):
        admit(operator, seen, _four()[0].capabilities)


def test_scripted_comparison_is_one_family_and_not_a_significance_claim() -> None:
    spec, solution = _four()
    report = run_comparison(spec, solution, [("C",)], partition="development", seed=1)
    assert report["llm_calls"] == 0
    assert report["backend"] == "scripted"
    assert report["family"] == "schneider"
    assert report["significant"] is False
    assert significance_allowed(1) is False
    assert report["paired_against_b0"]["B3"] == "loss"
    assert report["paired_against_b0"]["B5"] == "tie"
    assert report["paired_against_b0"]["B0"] if False else report["paired_against_b0"]["B6"] == "tie"
    frozen = evaluate_frozen(
        spec, solution, [("C",)], "delta_distance", report["applicability_rule"], seed=1, partition="confirmation"
    )
    assert frozen == tuple(report["objectives"]["B0"])
    with pytest.raises(RuntimeError, match="blind test"):
        refuse_heldout_selection("heldout")
    legacy = load_instance(DATA_ROOT / "c101C5.txt")
    assert partition_of(legacy) == "discovery"
    loaded = load_schneider_v2(DATA_ROOT / "c101C5.txt")
    assert loaded.family == "schneider"
    assert loaded.instance_id == "c101C5"
