"""Contracts the agent must be able to express. The evaluator is unchanged."""
from __future__ import annotations

import copy

from evrptw_autolab.agentic_v2.actions import solution_from_plan
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


def _bezzi() -> ProblemSpecV2:
    nodes = (
        NodeV2("D", "depot", 0, 0, charge_technologies=("0",)),
        NodeV2("C", "customer", 1, 0, demand=1),
    )
    matrix = {
        "D": {"D": 0.0, "C": 4.0},
        "C": {"D": 4.0, "C": 0.0},
    }
    return ProblemSpecV2(
        instance_id="bezzi_depot_charge",
        family="bezzi",
        capabilities=CapabilityFlags(
            battery=True,
            partial_recharge=True,
            multiple_charge_technologies=True,
            matrix_distances=True,
            euclidean_distances=False,
        ),
        nodes=nodes,
        vehicle_types=(
            VehicleTypeV2(
                "EV",
                capacity=10,
                battery_capacity=10,
                is_electric=True,
                metadata={"charging_techs": {"0": {"gamma": 1.0, "rho": 0.0}}},
            ),
        ),
        depot_ids=("D",),
        objective="minimize_recharge_cost",
        metadata={"fixed_recharge_cost": 3.0, "energy_matrix": matrix, "travel_time_matrix": matrix},
    )


def test_agent_can_express_a_feasible_bezzi_depot_charge() -> None:
    spec = _bezzi()
    solution, errors = solution_from_plan(
        spec,
        {
            "routes": [
                {
                    "vehicle_type": "EV",
                    "customers": ["C"],
                    "depot_charge": {"charge_amount": 8.0, "charge_technology": "0"},
                }
            ]
        },
    )
    assert errors == []
    departure = solution.routes[0][0]
    assert departure.event == "depot"
    assert departure.charge_amount == 8.0
    assert departure.charge_technology == "0"
    report = evaluate_solution_v2(spec, solution)
    assert report.feasible, [item.detail for item in report.violations]
    assert report.objective == 11.0
    assert solution.routes[0][0].charge_amount == 8.0


def test_failed_transaction_does_not_change_the_incumbent() -> None:
    from evrptw_autolab.agentic_v2.actions import apply_transaction

    spec = _bezzi()
    solution, _errors = solution_from_plan(
        spec,
        {
            "routes": [
                {
                    "vehicle_type": "EV",
                    "customers": ["C"],
                    "depot_charge": {"charge_amount": 8.0, "charge_technology": "0"},
                }
            ]
        },
    )
    before = copy.deepcopy(solution.routes)
    kept, errors, committed = apply_transaction(
        spec,
        solution,
        {"moves": [{"op": "relocate", "customer": "missing", "to_route": 0, "position": 1}]},
    )
    assert committed is False
    assert any(item.startswith("unknown_customer") for item in errors)
    assert [[stop.node_id for stop in route] for route in kept.routes] == [
        [stop.node_id for stop in route] for route in before
    ]
    assert kept.routes[0][0].charge_amount == 8.0


def test_pickup_delivery_pair_moves_together() -> None:
    from evrptw_autolab.agentic_v2.actions import apply_transaction

    spec = ProblemSpecV2(
        instance_id="pd_pair",
        family="goeke",
        capabilities=CapabilityFlags(pickup_delivery=True, capacity=True, time_windows=True, euclidean_distances=True),
        nodes=(
            NodeV2("D", "depot", 0, 0, due_time=1000),
            NodeV2("P", "pickup", 1, 0, demand=1, due_time=1000, partner_id="L"),
            NodeV2("L", "delivery", 2, 0, demand=-1, due_time=1000, partner_id="P"),
            NodeV2("Q", "pickup", 0, 1, demand=1, due_time=1000, partner_id="M"),
            NodeV2("M", "delivery", 0, 2, demand=-1, due_time=1000, partner_id="Q"),
        ),
        vehicle_types=(VehicleTypeV2("EV", capacity=10, battery_capacity=None, is_electric=False, is_conventional=True, velocity=1),),
        depot_ids=("D",),
        requests=(RequestV2("r1", "P", "L", 1.0), RequestV2("r2", "Q", "M", 1.0)),
    )
    solution = SolutionV2(
        routes=[
            [
                RouteStopV2("D", "EV", "depot"),
                RouteStopV2("P", "EV", "pickup"),
                RouteStopV2("L", "EV", "delivery"),
                RouteStopV2("Q", "EV", "pickup"),
                RouteStopV2("M", "EV", "delivery"),
                RouteStopV2("D", "EV", "depot"),
            ],
            [RouteStopV2("D", "EV", "depot"), RouteStopV2("D", "EV", "depot")],
        ],
        vehicle_assignments=["EV", "EV"],
    )
    from evrptw_autolab.agentic_v2.actions import apply_relocations

    trial = copy.deepcopy(solution)
    relocate_errors = apply_relocations(
        spec,
        trial,
        {"moves": [{"op": "relocate", "customer": "L", "to_route": 1, "position": 1}]},
    )
    assert relocate_errors == []
    moved = [stop.node_id for stop in trial.routes[1]]
    assert moved.index("P") < moved.index("L")
    moved_report = evaluate_solution_v2(spec, trial)
    assert moved_report.feasible, [item.detail for item in moved_report.violations]
    kept, errors, committed = apply_transaction(
        spec,
        solution,
        {"moves": [{"op": "relocate", "customer": "L", "to_route": 1, "position": 1}]},
    )
    assert committed is False
    assert errors == ["rejected_objective_regression"]
    assert [stop.node_id for stop in kept.routes[0]] == ["D", "P", "L", "Q", "M", "D"]


def test_problem_context_exposes_bezzi_matrices_and_empty_start() -> None:
    from evrptw_autolab.agentic_v2.instance_context import problem_context

    context = problem_context(_bezzi())
    assert context["initial_battery_rule"] == "empty_until_explicit_depot_charge"
    assert context["uses_published_matrices"] is True
    assert context["energy_matrix"]["D"]["C"] == 4.0
    assert context["euclidean_distances"] is False


def test_missing_charges_are_completed_by_the_labeled_dp() -> None:
    from evrptw_autolab.agentic_v2.charge_repair import complete_missing_charges

    spec = _bezzi()
    solution, _errors = solution_from_plan(spec, {"routes": [{"vehicle_type": "EV", "customers": ["C"]}]})
    assert solution.routes[0][0].charge_amount is None
    planned, mode = complete_missing_charges(spec, solution)
    assert mode == "deterministic_bezzi_recharge_dp"
    assert planned.metadata["classical_alns"] is False
    assert planned.metadata["attribution"] == "agentic_customer_plan_with_deterministic_charge_repair"
    report = evaluate_solution_v2(spec, planned)
    assert report.feasible, [item.detail for item in report.violations]
    assert planned.routes[0][0].charge_amount == 8.0


def test_partial_vehicle_assignment_uses_each_resolved_type() -> None:
    spec = ProblemSpecV2(
        instance_id="mixed_fleet",
        family="hiermann",
        capabilities=CapabilityFlags(heterogeneous_fleet=True, capacity=True, euclidean_distances=True),
        nodes=(
            NodeV2("D", "depot", 0, 0, due_time=1000),
            NodeV2("A", "customer", 1, 0, demand=1, due_time=1000),
            NodeV2("B", "customer", 0, 1, demand=1, due_time=1000),
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
            VehicleTypeV2(
                "BEV",
                capacity=10,
                battery_capacity=50,
                consumption_rate=0,
                velocity=1,
                is_electric=True,
                fixed_cost=5,
            ),
        ),
        depot_ids=("D",),
        metadata={"energy_prices": {"fossil-fuel": 1.0, "electricity": 1.0}},
    )
    solution = SolutionV2(
        routes=[
            [
                RouteStopV2("D", "ICE", "depot"),
                RouteStopV2("A", "ICE", "visit"),
                RouteStopV2("D", "ICE", "depot"),
            ],
            [
                RouteStopV2("D", "BEV", "depot"),
                RouteStopV2("B", "BEV", "visit"),
                RouteStopV2("D", "BEV", "depot"),
            ],
        ],
        vehicle_assignments=["ICE"],
    )
    report = evaluate_solution_v2(spec, solution)
    assert report.feasible, [item.detail for item in report.violations]
    assert report.objective_components["fixed_cost"] == 105.0
