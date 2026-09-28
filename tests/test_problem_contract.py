from math import hypot

from tests.conftest import DATA_ROOT

from evrptw_autolab.problem.evaluator import evaluate_solution
from evrptw_autolab.problem.objective import lex_key
from evrptw_autolab.problem.physics import (
    distance,
    energy_required,
    full_recharge,
    propagate_route,
    travel_time,
)
from evrptw_autolab.problem.schneider import discover_instances
from evrptw_autolab.problem.types import CandidateSolution


def test_discovers_ninety_two_instances() -> None:
    paths = discover_instances(DATA_ROOT)
    assert len(paths) == 92


def test_parser_c101c5(c101c5) -> None:
    assert c101c5.instance_id == "c101C5"
    assert c101c5.metadata["family"] == "C1"
    assert len(c101c5.customers) == 5
    assert c101c5.n_customers == 5
    assert all(node.id in c101c5.customer_ids for node in c101c5.customers)
    assert c101c5.stations
    assert c101c5.vehicle.capacity == 200.0
    assert c101c5.vehicle.battery_capacity == 77.75
    assert c101c5.vehicle.consumption_rate == 1.0
    assert c101c5.vehicle.velocity == 1.0
    assert c101c5.vehicle.inverse_refuel_rate == 3.47


def test_distance_travel_energy(c101c5) -> None:
    depot = c101c5.depot
    customer = c101c5.node_map["C30"]
    expected = hypot(depot.x - customer.x, depot.y - customer.y)
    assert distance(depot, customer) == expected
    assert travel_time(depot, customer, c101c5.vehicle) == expected / c101c5.vehicle.velocity
    assert energy_required(depot, customer, c101c5.vehicle) == expected * c101c5.vehicle.consumption_rate


def test_full_recharge(c101c5) -> None:
    decision = full_recharge(c101c5.vehicle, 10.0)
    assert decision.battery_departure == c101c5.vehicle.battery_capacity
    assert decision.energy_charged == c101c5.vehicle.battery_capacity - 10.0
    assert decision.duration == decision.energy_charged * c101c5.vehicle.inverse_refuel_rate


def test_propagate_and_capacity(c101c5) -> None:
    route = [c101c5.depot_id, "C30", c101c5.depot_id]
    stops = propagate_route(c101c5, route)
    assert stops[1].load == 10.0
    assert stops[1].load < c101c5.vehicle.capacity
    assert stops[-1].node_id == c101c5.depot_id


def test_canonical_evaluation_dedicated_routes(c101c5) -> None:
    routes = [[c101c5.depot_id, cid, c101c5.depot_id] for cid in c101c5.customer_ids]
    report = evaluate_solution(c101c5, CandidateSolution(routes))
    assert report.parse_ok
    assert report.all_customers_served_once
    assert report.vehicles == 5
    assert lex_key(report)[1] == 5


def test_unserved_is_infeasible(c101c5) -> None:
    report = evaluate_solution(c101c5, CandidateSolution([[c101c5.depot_id, c101c5.depot_id]]))
    assert not report.feasible
    assert len(report.unserved) == 5
