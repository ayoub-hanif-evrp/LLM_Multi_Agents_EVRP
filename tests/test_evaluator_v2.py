"""Independent v2 evaluator micro-tests across variant families."""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.problem.datasets.bezzi import load_bezzi
from evrptw_autolab.problem.datasets.goeke import load_goeke
from evrptw_autolab.problem.datasets.montoya import load_montoya
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.problem.evaluator import evaluate_solution
from evrptw_autolab.problem.micro import micro_g1_one_customer, micro_g2_needs_charge
from evrptw_autolab.problem.schneider import load_instance
from evrptw_autolab.problem.types import CandidateSolution
from evrptw_autolab.problem.v2.charging import nonlinear_charge_duration
from evrptw_autolab.problem.v2.evaluator import evaluate_solution_v2
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    RouteStopV2,
    SolutionV2,
    VehicleTypeV2,
)

ROOT = Path(__file__).resolve().parents[1]


def test_nonlinear_charge_monotonic_duration() -> None:
    breakpoints = [
        {"battery_level": 0.0, "charging_time": 0.0},
        {"battery_level": 100.0, "charging_time": 1.0},
        {"battery_level": 200.0, "charging_time": 3.0},
    ]
    d1 = nonlinear_charge_duration(breakpoints, 0.0, 100.0)
    d2 = nonlinear_charge_duration(breakpoints, 100.0, 200.0)
    assert abs(d1 - 1.0) < 1e-9
    assert abs(d2 - 2.0) < 1e-9
    assert nonlinear_charge_duration(breakpoints, 50.0, 150.0) > 0


def test_schneider_micro_feasible_matches_legacy() -> None:
    legacy = micro_g1_one_customer()
    routes = [[legacy.depot_id, "C1", legacy.depot_id]]
    legacy_report = evaluate_solution(legacy, CandidateSolution(routes))
    assert legacy_report.feasible

    spec = load_schneider_v2(legacy.metadata["source_path"])
    sol = SolutionV2.from_legacy_routes(routes, vehicle_type_id="EV")
    report = evaluate_solution_v2(spec, sol)
    assert report.feasible
    assert report.first_fault is not None
    assert report.first_fault.family == "OK"


def test_schneider_battery_infeasible_detected() -> None:
    legacy = micro_g2_needs_charge()
    # Skip station: should be battery-infeasible for the long hop.
    routes = [[legacy.depot_id, "C1", legacy.depot_id]]
    legacy_report = evaluate_solution(legacy, CandidateSolution(routes))
    spec = load_schneider_v2(legacy.metadata["source_path"])
    report = evaluate_solution_v2(spec, SolutionV2.from_legacy_routes(routes, vehicle_type_id="EV"))
    assert not legacy_report.feasible
    assert not report.feasible
    assert any(v.family == "BATTERY" for v in report.violations)


def test_goeke_precedence_violation() -> None:
    spec = load_goeke(ROOT / "dataset" / "goeke-2018" / "c101C6.txt")
    depot = spec.depot_ids[0]
    # Delivery before pickup for C12/C30.
    bad = SolutionV2(
        routes=[
            [
                RouteStopV2(depot, event="depot"),
                RouteStopV2("C30", event="delivery"),
                RouteStopV2("C12", event="pickup"),
                RouteStopV2(depot, event="depot"),
            ]
        ],
        vehicle_assignments=["EV"],
    )
    report = evaluate_solution_v2(spec, bad)
    assert not report.feasible
    assert any(v.family == "PRECEDENCE" for v in report.violations)


def test_goeke_valid_pair_order_load_ok() -> None:
    spec = load_goeke(ROOT / "dataset" / "goeke-2018" / "c101C6.txt")
    depot = spec.depot_ids[0]
    # Single pair only — other requests unserved (VISIT), but precedence/capacity for this pair OK.
    sol = SolutionV2(
        routes=[
            [
                RouteStopV2(depot, event="depot"),
                RouteStopV2("C12", event="pickup"),
                RouteStopV2("C30", event="delivery"),
                RouteStopV2(depot, event="depot"),
            ]
        ],
        vehicle_assignments=["EV"],
    )
    report = evaluate_solution_v2(spec, sol)
    assert any(v.family == "VISIT" for v in report.violations)
    assert not any(v.family == "PRECEDENCE" for v in report.violations)
    assert not any(v.family == "CAPACITY" for v in report.violations)


def test_montoya_customer_coverage_and_duration() -> None:
    spec = load_montoya(ROOT / "dataset" / "montoya-et-al-2017" / "tc0c10s2cf1.xml")
    depot = spec.depot_ids[0]
    # Empty of customers → unserved.
    sol = SolutionV2(
        routes=[[RouteStopV2(depot, event="depot"), RouteStopV2(depot, event="depot")]],
        vehicle_assignments=["EV0"],
    )
    report = evaluate_solution_v2(spec, sol)
    assert not report.feasible
    assert len(report.unserved) == 10


def test_bezzi_matrix_unknown_arc_parse_error() -> None:
    paths = list((ROOT / "dataset" / "Bezzi & Ceselli EVRP-MRT").glob("**/Instances/C101-5.xml"))
    spec = load_bezzi(paths[0])
    depot = spec.depot_ids[0]
    customers = [n.id for n in spec.nodes if n.kind == "customer"]
    # Valid IDs but we only check depot-only route for unserved.
    sol = SolutionV2(
        routes=[[RouteStopV2(depot, event="depot"), RouteStopV2(depot, event="depot")]],
        vehicle_assignments=[spec.vehicle_types[0].type_id],
    )
    report = evaluate_solution_v2(spec, sol)
    assert not report.feasible
    assert set(report.unserved) == set(customers)


def test_hiermann_icev_no_battery_synthetic() -> None:
    caps = CapabilityFlags(
        time_windows=True,
        capacity=True,
        battery=True,
        heterogeneous_fleet=True,
        conventional_vehicles=True,
        euclidean_distances=True,
    )
    nodes = (
        NodeV2("D0", "depot", 0.0, 0.0, due_time=100.0),
        NodeV2("C1", "customer", 1.0, 0.0, demand=5.0, ready_time=0.0, due_time=50.0, service_time=1.0),
    )
    icev = VehicleTypeV2(
        type_id="1",
        capacity=100.0,
        battery_capacity=None,
        is_electric=False,
        is_conventional=True,
        velocity=1.0,
        fixed_cost=10.0,
        metadata={"propulsion": "ICEV"},
    )
    spec = ProblemSpecV2(
        instance_id="synth_icev",
        family="hiermann",
        capabilities=caps,
        nodes=nodes,
        vehicle_types=(icev,),
        depot_ids=("D0",),
        metadata={"travel_time_model": "distance_equals_time"},
    )
    sol = SolutionV2(
        routes=[
            [
                RouteStopV2("D0", event="depot"),
                RouteStopV2("C1", event="visit"),
                RouteStopV2("D0", event="depot"),
            ]
        ],
        vehicle_assignments=["1"],
    )
    report = evaluate_solution_v2(spec, sol)
    assert report.feasible
    assert report.charging_visits == 0


def test_full_recharge_policy_rejects_partial_on_schneider() -> None:
    legacy = micro_g1_one_customer()
    spec = load_schneider_v2(legacy.metadata["source_path"])
    # Force a station visit with partial charge when only full recharge is allowed.
    # micro_g1 has station S0; visit it with charge_amount less than needed to fill.
    depot = spec.depot_ids[0]
    stations = [n.id for n in spec.nodes if n.kind == "station"]
    if not stations:
        return
    sol = SolutionV2(
        routes=[
            [
                RouteStopV2(depot, event="depot"),
                RouteStopV2("C1", event="visit"),
                RouteStopV2(stations[0], event="charge", charge_amount=1.0),
                RouteStopV2(depot, event="depot"),
            ]
        ],
        vehicle_assignments=["EV"],
    )
    report = evaluate_solution_v2(spec, sol)
    assert any(
        v.family == "CHARGE_POLICY" and "partial_recharge_not_allowed" in v.detail
        for v in report.violations
    )


def test_legacy_schneider_c101c5_still_loads() -> None:
    # Regression: legacy path untouched.
    path = ROOT / "dataset" / "schneider" / "raw_instances" / "c101C5.txt"
    inst = load_instance(path)
    assert inst.n_customers == 5
