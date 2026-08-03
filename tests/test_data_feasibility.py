"""Dataset discovery, Solomon parsing, feasibility, and merged-init determinism."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from chargecegis.alns import solution_hash
from chargecegis.charging import LinearFullRechargeModel
from chargecegis.construction import construct_initial_solution, construct_merged_initial_solution
from chargecegis.data import discover_instances, load_instance, parse_solomon
from chargecegis.feasibility import evaluate_feasibility, evaluate_objective
from chargecegis.problem import Route, Vehicle

ROOT = Path(__file__).resolve().parents[1]
SCHNEIDER = ROOT / "dataset" / "schneider" / "raw_instances"


@pytest.fixture(scope="module")
def small_instance():
    return load_instance(SCHNEIDER / "c101C5.txt")


@pytest.fixture(scope="module")
def small_solution(small_instance):
    result = construct_initial_solution(small_instance)
    assert result.feasible and result.solution is not None
    return result.solution


def test_discover_92_instances_36_small_56_large() -> None:
    paths = discover_instances(SCHNEIDER)
    assert len(paths) == 92
    assert all(p.name.lower() != "readme.txt" for p in paths)
    instances = [load_instance(p) for p in paths]
    small = [i for i in instances if i.metadata["scale"] == "small"]
    large = [i for i in instances if i.metadata["scale"] == "large"]
    assert len(small) == 36
    assert len(large) == 56


def test_instance_id_family_and_vehicle_parameters(small_instance) -> None:
    assert small_instance.instance_id == "c101C5"
    assert small_instance.metadata["family"] == "C1"
    assert small_instance.metadata["scale"] == "small"
    assert small_instance.vehicle.freight_capacity == 200.0
    assert small_instance.vehicle.battery_capacity == pytest.approx(77.75)
    assert small_instance.vehicle.consumption_rate > 0
    assert small_instance.vehicle.velocity > 0


def test_missing_vehicle_parameters_raise() -> None:
    text = "StringId Type x y demand ReadyTime DueDate ServiceTime\nD0 d 0 0 0 0 100 0\n"
    with pytest.raises(ValueError, match="Missing Schneider vehicle parameters"):
        parse_solomon(text)


def test_full_recharge_departs_full_and_partial_recharge_rejected(small_instance, small_solution) -> None:
    model = LinearFullRechargeModel()
    for route in small_solution.routes:
        for stop in route.schedule:
            if stop.node_id in small_instance.station_ids:
                assert stop.battery_on_departure == pytest.approx(small_instance.vehicle.battery_capacity)
    vehicle = Vehicle(freight_capacity=100, battery_capacity=50, initial_soc=50,
                      consumption_rate=1, velocity=1, inverse_refuel_rate=1)
    errors = model.validate_decision(vehicle, battery_on_arrival=10.0, energy_charged=20.0)
    assert "partial_recharge_not_allowed" in errors or "station_must_depart_full" in errors


def test_feasibility_report_clean_and_detects_missing_customer(small_instance, small_solution) -> None:
    report = evaluate_feasibility(small_instance, small_solution)
    assert report.feasible
    assert report.violation_count == 0

    truncated_routes = tuple(
        Route(r.vehicle_index, r.node_ids[:-2] + (small_instance.depot_id,)) for r in small_solution.routes[:1]
    ) + small_solution.routes[1:]
    broken = replace(small_solution, routes=truncated_routes)
    assert not evaluate_feasibility(small_instance, broken).feasible


def test_evaluate_objective_lexicographic_fields(small_instance, small_solution) -> None:
    objective = evaluate_objective(small_instance, small_solution)
    assert objective.infeasibility_count == 0
    assert objective.unserved_customers == 0
    assert objective.vehicles_used == len(small_solution.routes)
    assert objective.total_distance > 0


def test_merged_initial_construction_is_deterministic_for_a_fixed_seed(small_instance) -> None:
    """Equal-budget ranking methods share one merged initial solution per (instance, seed); this
    is only a fair comparison if construction is a pure function of the seed."""
    first = construct_merged_initial_solution(small_instance, seed=0)
    second = construct_merged_initial_solution(small_instance, seed=0)
    assert first.feasible and second.feasible
    assert solution_hash(first.solution) == solution_hash(second.solution)
    assert len(first.solution.routes) <= len(construct_initial_solution(small_instance).solution.routes)
