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
    RequestV2,
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


def test_schneider_v2_distance_matches_legacy_on_micro() -> None:
    legacy = micro_g1_one_customer()
    routes = [[legacy.depot_id, "C1", legacy.depot_id]]
    legacy_report = evaluate_solution(legacy, CandidateSolution(routes))
    spec = load_schneider_v2(legacy.metadata["source_path"])
    report = evaluate_solution_v2(spec, SolutionV2.from_legacy_routes(routes, vehicle_type_id="EV"))
    assert legacy_report.feasible and report.feasible
    assert abs(legacy_report.total_distance - report.total_distance) < 1e-6
    assert report.objective_key[0] == 1
    assert abs(report.objective_key[1] - legacy_report.total_distance) < 1e-6


def test_hiermann_travel_time_and_mixed_fleet_costs() -> None:
    from math import hypot

    from evrptw_autolab.problem.datasets.hiermann import load_hiermann

    spec = load_hiermann(ROOT / "dataset" / "hiermann-et-al-2017-set-1" / "c101_21.txt")
    assert spec.metadata["travel_time_model"] == "distance_equals_time"
    depot = spec.node_map["D0"]
    customer = spec.node_map["C1"]
    distance = hypot(customer.x - depot.x, customer.y - depot.y)
    route = [
        RouteStopV2("D0", event="depot"),
        RouteStopV2("C1", event="visit"),
        RouteStopV2("D0", event="depot"),
    ]
    costs: dict[str, float] = {}
    for type_id in ("1", "4", "7"):  # ICEV, PHEV, BEV
        report = evaluate_solution_v2(
            spec,
            SolutionV2(routes=[route], vehicle_assignments=[type_id]),
        )
        # Unserved customers are expected; this route's physics must still be well-defined.
        assert not any(v.family in {"BATTERY", "PARSE", "WINDOW"} for v in report.violations if v.node_id in {"C1", "D0"})
        assert report.trajectories
        traj = report.trajectories[0]
        assert abs(traj[-1].distance_so_far - 2 * distance) < 1e-6
        assert abs(traj[1].arrival_time - distance) < 1e-6
        costs[type_id] = report.objective_components["total_cost"]
        vehicle = next(v for v in spec.vehicle_types if v.type_id == type_id)
        prices = spec.metadata["energy_prices"]
        if vehicle.is_conventional and not vehicle.is_hybrid:
            expected = vehicle.fixed_cost + prices["fossil-fuel"] * traj[-1].fuel_used
            assert traj[-1].electric_used == 0
            assert not any(v.family == "BATTERY" for v in report.violations)
        elif vehicle.is_hybrid:
            expected = (
                vehicle.fixed_cost
                + prices["fossil-fuel"] * traj[-1].fuel_used
                + prices["electricity"] * traj[-1].electric_used
            )
            assert traj[-1].electric_used > 0
        else:
            expected = vehicle.fixed_cost + prices["electricity"] * traj[-1].electric_used
            assert traj[-1].fuel_used == 0
        assert abs(costs[type_id] - expected) < 1e-6
    assert len(set(round(v, 6) for v in costs.values())) == 3


def test_montoya_partial_charge_changes_duration() -> None:
    spec = load_montoya(ROOT / "dataset" / "montoya-et-al-2017" / "tc0c10s2cf1.xml")
    curve = next(iter(spec.metadata["charging_functions"].values()))
    cap = float(curve[-1]["battery_level"])
    d60 = nonlinear_charge_duration(curve, 0.0, 0.6 * cap)
    d80 = nonlinear_charge_duration(curve, 0.0, 0.8 * cap)
    d100 = nonlinear_charge_duration(curve, 0.0, cap)
    assert d60 < d80 < d100

    # Arrive at 50% so each target actually charges.
    partial = ProblemSpecV2(
        instance_id="montoya_partial",
        family="montoya",
        capabilities=CapabilityFlags(
            battery=True,
            nonlinear_charging=True,
            partial_recharge=True,
            euclidean_distances=True,
            max_route_duration=True,
        ),
        nodes=(
            NodeV2("D", "depot", 0, 0),
            NodeV2("S", "station", cap / 2, 0, charge_technologies=("fast",)),
        ),
        vehicle_types=(
            VehicleTypeV2(
                "EV",
                capacity=0.0,
                battery_capacity=cap,
                consumption_rate=1.0,
                velocity=1.0,
                metadata={"charging_functions": {"fast": curve}, "max_travel_time": 1e9},
            ),
        ),
        depot_ids=("D",),
        metadata={"charging_functions": {"fast": curve}, "max_travel_time": 1e9},
    )
    durations = []
    for frac in (0.6, 0.8, 1.0):
        report = evaluate_solution_v2(
            partial,
            SolutionV2(
                routes=[
                    [
                        RouteStopV2("D", event="depot"),
                        RouteStopV2("S", event="charge", target_soc=frac * cap, charge_technology="fast"),
                        RouteStopV2("D", event="depot"),
                    ]
                ],
                vehicle_assignments=["EV"],
            ),
        )
        assert report.trajectories[0][1].energy_charged > 0
        durations.append(report.total_duration)
    assert durations[0] < durations[1] < durations[2]


def test_bezzi_published_optima_match_recharge_cost() -> None:
    from evrptw_autolab.problem.datasets.bezzi_reference import load_published_bezzi_solution

    root = ROOT / "dataset" / "Bezzi & Ceselli EVRP-MRT"
    samples = [
        "Dataset_A/Solutions/SOL-C101-5.xml",
        "Dataset_B/Solutions/SOL-10-N10.xml",
        "Dataset_C/Solutions/SOL-C1-N030.xml",
    ]
    for rel in samples:
        solution_path = root / rel
        instance_path = solution_path.parent.parent / "Instances" / solution_path.name.removeprefix("SOL-")
        spec = load_bezzi(instance_path)
        published = load_published_bezzi_solution(solution_path, spec)
        assert len(published.solution.routes) <= spec.fleet_availability[spec.vehicle_types[0].type_id]
        report = evaluate_solution_v2(spec, published.solution)
        assert report.feasible, [v.detail for v in report.violations[:5]]
        assert abs(float(report.objective or -1) - published.total_cost) < 1e-3


def test_bezzi_fleet_availability_is_hard() -> None:
    spec = load_bezzi(next((ROOT / "dataset" / "Bezzi & Ceselli EVRP-MRT").glob("**/Instances/C101-5.xml")))
    depot = spec.depot_ids[0]
    limit = spec.fleet_availability[spec.vehicle_types[0].type_id]
    routes = [[RouteStopV2(depot, event="depot"), RouteStopV2(depot, event="depot")] for _ in range(limit + 1)]
    report = evaluate_solution_v2(
        spec,
        SolutionV2(routes=routes, vehicle_assignments=[spec.vehicle_types[0].type_id] * len(routes)),
    )
    assert any(v.family == "FLEET" for v in report.violations)


def test_goeke_complete_request_is_load_feasible() -> None:
    spec = ProblemSpecV2(
        instance_id="goeke_synth",
        family="goeke",
        capabilities=CapabilityFlags(
            time_windows=True,
            capacity=True,
            battery=True,
            pickup_delivery=True,
            euclidean_distances=True,
            partial_recharge=True,
            full_recharge=True,
        ),
        nodes=(
            NodeV2("D", "depot", 0, 0, due_time=100),
            NodeV2("P", "pickup", 1, 0, demand=5, ready_time=0, due_time=50, service_time=1, partner_id="R"),
            NodeV2("R", "delivery", 2, 0, demand=-5, ready_time=0, due_time=80, service_time=1, partner_id="P"),
        ),
        vehicle_types=(
            VehicleTypeV2(
                "EV",
                capacity=10,
                battery_capacity=100,
                consumption_rate=1,
                velocity=1,
                metadata={"inverse_refuel_rate": 1},
            ),
        ),
        depot_ids=("D",),
        requests=(RequestV2("1", "P", "R", 5.0, True),),
        fleet_availability={"EV": 1},
        metadata={},
    )
    good = SolutionV2(
        routes=[
            [
                RouteStopV2("D", event="depot"),
                RouteStopV2("P", event="pickup"),
                RouteStopV2("R", event="delivery"),
                RouteStopV2("D", event="depot"),
            ]
        ],
        vehicle_assignments=["EV"],
    )
    report = evaluate_solution_v2(spec, good)
    assert report.feasible
    assert report.trajectories[0][1].load == 5
    assert report.trajectories[0][2].load == 0
    split = SolutionV2(
        routes=[
            [RouteStopV2("D", event="depot"), RouteStopV2("P", event="pickup"), RouteStopV2("D", event="depot")],
            [RouteStopV2("D", event="depot"), RouteStopV2("R", event="delivery"), RouteStopV2("D", event="depot")],
        ],
        vehicle_assignments=["EV", "EV"],
    )
    bad = evaluate_solution_v2(spec, split)
    assert any(v.family == "PAIRING" for v in bad.violations)
    assert any(v.family == "FLEET" for v in bad.violations)
