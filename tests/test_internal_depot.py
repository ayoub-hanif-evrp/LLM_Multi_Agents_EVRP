"""A route may contain the depot only as its first and last stop."""
from __future__ import annotations

from evrptw_autolab.problem.evaluator import evaluate_solution, first_fault
from evrptw_autolab.problem.micro import (
    micro_g1_one_customer,
    micro_g2_needs_charge,
    micro_g3_two_customers,
)
from evrptw_autolab.problem.types import CandidateSolution


def test_micro_instances_match_the_contract() -> None:
    one = micro_g1_one_customer()
    depot, customer = one.depot_id, one.customer_ids[0]
    assert first_fault(one, CandidateSolution([[depot, customer, depot]]))["family"] == "OK"

    charge = micro_g2_needs_charge()
    depot, customer, station = charge.depot_id, charge.customer_ids[0], charge.station_ids[0]
    assert first_fault(charge, CandidateSolution([[depot, customer, depot]]))["family"] == "BATTERY"
    assert first_fault(charge, CandidateSolution([[depot, station, customer, depot]]))["family"] == "OK"


def test_internal_depot_is_not_one_vehicle() -> None:
    instance = micro_g3_two_customers()
    depot = instance.depot_id
    first, second = instance.customer_ids
    invalid = CandidateSolution(routes=[[depot, first, depot, second, depot]])
    packet = first_fault(instance, invalid)
    assert packet["family"] == "DEPOT"
    assert "only at the start and end" in packet["detail"]
    report = evaluate_solution(instance, invalid)
    assert report.feasible is False
    assert report.depot_violations >= 1

    separate = CandidateSolution(routes=[[depot, first, depot], [depot, second, depot]])
    assert first_fault(instance, separate)["family"] == "OK"
    assert evaluate_solution(instance, separate).feasible is True
