"""Regression tests for the five seed-7 classical pilot failures."""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.bezzi import load_bezzi
from evrptw_autolab.problem.datasets.goeke import load_goeke
from evrptw_autolab.problem.datasets.montoya import load_montoya
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.problem.v2.types import RouteStopV2, SolutionV2

ROOT = Path(__file__).resolve().parents[1]


def _assert_route_invariants(spec, solution, report) -> None:
    assert report.feasible, (report.first_fault, report.explanation)
    served = {s.node_id for route in solution.routes for s in route}
    for node in spec.nodes:
        if node.kind in {"customer", "pickup", "delivery"}:
            assert node.id in served, node.id
    for traj in report.trajectories:
        for state in traj:
            assert state.battery_arrival >= -1e-6, (state.node_id, state.battery_arrival)
    if spec.capabilities.max_route_duration:
        limit = float(spec.metadata.get("max_travel_time") or 10.0)
        for traj in report.trajectories:
            assert traj[-1].departure_time <= limit + 1e-5, traj[-1].departure_time


def test_montoya_tc0c10s2cf1_feasible() -> None:
    spec = load_montoya(ROOT / "dataset" / "montoya-et-al-2017" / "tc0c10s2cf1.xml")
    sol = solve_classical(spec, seed=7, time_limit_s=10.0, alns_iterations=60)
    report = evaluate(spec, sol)
    _assert_route_invariants(spec, sol, report)


def test_montoya_tc0c10s3cf1_feasible() -> None:
    spec = load_montoya(ROOT / "dataset" / "montoya-et-al-2017" / "tc0c10s3cf1.xml")
    sol = solve_classical(spec, seed=7, time_limit_s=10.0, alns_iterations=60)
    report = evaluate(spec, sol)
    _assert_route_invariants(spec, sol, report)


def test_schneider_r105c5_feasible() -> None:
    spec = load_schneider_v2(ROOT / "dataset" / "schneider" / "raw_instances" / "r105C5.txt")
    sol = solve_classical(spec, seed=7, time_limit_s=8.0, alns_iterations=80)
    report = evaluate(spec, sol)
    _assert_route_invariants(spec, sol, report)
    assert report.objective_key[0] <= 3.0


def test_goeke_rc105c6_feasible_pd() -> None:
    spec = load_goeke(ROOT / "dataset" / "goeke-2018" / "rc105C6.txt")
    sol = solve_classical(spec, seed=7, time_limit_s=10.0, alns_iterations=60)
    report = evaluate(spec, sol)
    _assert_route_invariants(spec, sol, report)
    for req in spec.requests:
        for route in sol.routes:
            ids = [s.node_id for s in route]
            if req.pickup_id in ids:
                assert req.delivery_id in ids
                assert ids.index(req.pickup_id) < ids.index(req.delivery_id)


def test_bezzi_r105_5_has_charge_decisions() -> None:
    spec = load_bezzi(ROOT / "dataset" / "Bezzi & Ceselli EVRP-MRT" / "Dataset_A" / "Instances" / "R105-5.xml")
    sol = solve_classical(spec, seed=7, time_limit_s=12.0, alns_iterations=60)
    report = evaluate(spec, sol)
    assert report.feasible, (report.first_fault, report.explanation)
    assert not any(v.family == "CHARGE_POLICY" for v in report.violations)
    # Feasible Bezzi routes must carry explicit charge annotations where stations appear.
    for route in sol.routes:
        for stop in route:
            if spec.node_map[stop.node_id].kind == "station":
                assert stop.charge_amount is not None or stop.charge_technology is not None


def test_local_search_preserves_vehicle_assignment_alignment() -> None:
    """Dropping a middle empty route must not scramble remaining vehicle types."""
    from evrptw_autolab.backbone.local_search import _drop_empty_routes

    sol = SolutionV2(
        routes=[
            [
                RouteStopV2("D0", vehicle_type_id="A", event="depot"),
                RouteStopV2("C1", event="visit"),
                RouteStopV2("D0", vehicle_type_id="A", event="depot"),
            ],
            [
                RouteStopV2("D0", vehicle_type_id="B", event="depot"),
                RouteStopV2("D0", vehicle_type_id="B", event="depot"),
            ],
            [
                RouteStopV2("D0", vehicle_type_id="C", event="depot"),
                RouteStopV2("C2", event="visit"),
                RouteStopV2("D0", vehicle_type_id="C", event="depot"),
            ],
        ],
        vehicle_assignments=["A", "B", "C"],
    )
    _drop_empty_routes(sol, "A")
    assert sol.vehicle_assignments == ["A", "C"]
    assert [r[1].node_id for r in sol.routes] == ["C1", "C2"]
