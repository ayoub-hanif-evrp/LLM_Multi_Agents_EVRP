"""Feasibility and timeout compliance are reported as separate facts."""
from __future__ import annotations

from evrptw_autolab.backbone.solver import ClassicalSolver
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    RouteStopV2,
    SolutionV2,
    VehicleTypeV2,
)


def _easy() -> ProblemSpecV2:
    return ProblemSpecV2(
        instance_id="status_micro",
        family="schneider",
        capabilities=CapabilityFlags(
            battery=True,
            full_recharge=True,
            time_windows=True,
            euclidean_distances=True,
        ),
        nodes=(
            NodeV2("D", "depot", 0, 0, due_time=10_000),
            NodeV2("C", "customer", 1, 0, demand=1, due_time=10_000),
        ),
        vehicle_types=(
            VehicleTypeV2(
                "EV",
                capacity=10,
                battery_capacity=100,
                consumption_rate=1,
                velocity=1,
                metadata={"inverse_refuel_rate": 1.0},
            ),
        ),
        depot_ids=("D",),
        objective="minimize_vehicles_then_distance",
    )


def _guard() -> ProblemSpecV2:
    return ProblemSpecV2(
        instance_id="status_guard",
        family="schneider",
        capabilities=CapabilityFlags(
            battery=True,
            full_recharge=True,
            time_windows=True,
            euclidean_distances=True,
        ),
        nodes=(
            NodeV2("D", "depot", 0, 0, due_time=10_000),
            NodeV2("C", "customer", 4, 0, demand=1, due_time=10_000),
            NodeV2("S", "station", 2, 2, due_time=10_000),
        ),
        vehicle_types=(
            VehicleTypeV2(
                "EV",
                capacity=10,
                battery_capacity=7,
                consumption_rate=1,
                velocity=1,
                metadata={"inverse_refuel_rate": 1.0},
            ),
        ),
        depot_ids=("D",),
        objective="minimize_vehicles_then_distance",
    )


def test_feasible_solution_returned_normally() -> None:
    sol = ClassicalSolver(seed=1, time_limit_s=8.0, alns_iterations=1, use_alns=False).solve(_easy())
    assert sol.metadata["solution_feasible"] is True
    assert sol.metadata["completed_within_budget"] is True
    assert sol.metadata["hard_timeout_triggered"] is False
    assert sol.metadata["worker_terminated"] is False
    assert sol.metadata["incumbent_available"] is True
    assert sol.metadata["parent_validated"] is True
    assert sol.metadata["return_status"] == "feasible_incumbent"
    assert sol.metadata["method_attribution"] == "classical_baseline"
    assert evaluate(_easy(), sol).feasible


def test_feasible_incumbent_preserved_after_timeout() -> None:
    sol = ClassicalSolver(
        seed=1,
        time_limit_s=6.0,
        alns_iterations=1,
        use_alns=False,
        debug_sleep_s=30.0,
    ).solve(_easy())
    assert sol.metadata["solution_feasible"] is True
    assert sol.metadata["completed_within_budget"] is False
    assert sol.metadata["hard_timeout_triggered"] is True
    assert sol.metadata["worker_terminated"] is True
    assert sol.metadata["incumbent_available"] is True
    assert sol.metadata["parent_validated"] is True
    assert sol.metadata["return_status"] == "timeout_with_feasible_incumbent"
    assert evaluate(_easy(), sol).feasible


def test_timeout_without_feasible_incumbent() -> None:
    sol = ClassicalSolver(
        seed=1,
        time_limit_s=0.6,
        alns_iterations=1,
        use_alns=False,
        debug_sleep_s=30.0,
        debug_publish_before_sleep=False,
    ).solve(_easy())
    assert sol.metadata["solution_feasible"] is False
    assert sol.metadata["incumbent_available"] is False
    assert sol.metadata["hard_timeout_triggered"] is True
    assert sol.metadata["completed_within_budget"] is False
    assert sol.metadata["return_status"] == "timeout_no_snapshot"


def test_worker_crash_is_not_a_feasible_result() -> None:
    sol = ClassicalSolver(seed=1, time_limit_s=5.0, alns_iterations=1, use_alns=False, debug_crash=True).solve(
        _easy()
    )
    assert sol.metadata["return_status"] == "worker_crash"
    assert sol.metadata["worker_terminated"] is True
    assert sol.metadata["solution_feasible"] is False
    assert sol.metadata["incumbent_available"] is False
    assert sol.metadata["completed_within_budget"] is False
    assert sol.metadata["hard_timeout_triggered"] is False


def test_invalid_worker_snapshot_is_rejected() -> None:
    sol = ClassicalSolver(
        seed=1,
        time_limit_s=5.0,
        alns_iterations=1,
        use_alns=False,
        debug_invalid_snapshot=True,
    ).solve(_easy())
    assert sol.metadata["return_status"] == "invalid_snapshot"
    assert sol.metadata["snapshot_status"] == "invalid"
    assert sol.metadata["parent_validated"] is False
    assert sol.metadata["solution_feasible"] is False
    assert sol.metadata["incumbent_available"] is False
    assert sol.metadata["completed_within_budget"] is False


def test_shorter_infeasible_policy_route_does_not_replace_feasible_incumbent() -> None:
    spec = _guard()
    feasible = SolutionV2(
        routes=[
            [
                RouteStopV2("D", vehicle_type_id="EV", event="depot"),
                RouteStopV2("S", vehicle_type_id="EV", event="charge"),
                RouteStopV2("C", vehicle_type_id="EV", event="visit"),
                RouteStopV2("D", vehicle_type_id="EV", event="depot"),
            ]
        ],
        vehicle_assignments=["EV"],
    )
    shorter = SolutionV2(
        routes=[
            [
                RouteStopV2("D", vehicle_type_id="EV", event="depot"),
                RouteStopV2("C", vehicle_type_id="EV", event="visit"),
                RouteStopV2("D", vehicle_type_id="EV", event="depot"),
            ]
        ],
        vehicle_assignments=["EV"],
    )
    assert evaluate(spec, feasible).feasible
    short_report = evaluate(spec, shorter)
    assert not short_report.feasible
    assert short_report.total_distance < evaluate(spec, feasible).total_distance
    solver = ClassicalSolver(seed=1, time_limit_s=1.0, use_alns=False, hard_timeout=False)
    box: dict = {}
    solver._publish(box, spec, feasible)
    solver._publish(box, spec, shorter)
    kept = evaluate(spec, box["incumbent"])
    assert kept.feasible
    assert [stop.node_id for stop in box["incumbent"].routes[0]] == ["D", "S", "C", "D"]


def test_inprocess_solve_records_scorer_calls() -> None:
    from evrptw_autolab.components.interfaces import DEFAULT_SOURCES
    from evrptw_autolab.components.loader import load_bundle

    bundle, errors = load_bundle(DEFAULT_SOURCES)
    assert not errors
    sol = ClassicalSolver(
        seed=1, time_limit_s=2.0, alns_iterations=1, use_alns=False, hard_timeout=False, policy=bundle
    ).solve(_easy())
    counts = sol.metadata.get("scorer_calls") or {}
    assert int(counts.get("insertion_score", 0)) > 0
    assert sol.metadata["method_attribution"] == "llm_policy_search"
    assert sol.metadata["solution_feasible"] is True
