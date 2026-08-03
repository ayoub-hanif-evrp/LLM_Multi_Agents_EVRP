"""Coupled move catalogue and charging reconstruction, on fixtures that *guarantee* the move
type / station-count outcome under test rather than hoping a real benchmark instance happens to
produce one."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import chargecegis.features as features_module
from chargecegis.construction import (
    ChargingReconstructionConfig,
    construct_initial_solution,
    reconstruct_route_charging,
)
from chargecegis.data import load_instance
from chargecegis.feasibility import evaluate_feasibility
from chargecegis.features import FEATURE_NAMES, compute_features
from chargecegis.moves import MoveType, apply_move, enumerate_moves
from chargecegis.problem import Instance, Node, NodeKind, Solution, Vehicle
from chargecegis.propagation import propagate_route

ROOT = Path(__file__).resolve().parents[1]
SCHNEIDER = ROOT / "dataset" / "schneider" / "raw_instances"


def _node(node_id: str, kind: NodeKind, x: float, *, demand: float = 0.0, due: float = 1_000.0) -> Node:
    return Node(node_id, kind, (x, 0.0), demand=demand, service_duration=0.0, ready_time=0.0, due_time=due)


def _generous_instance() -> Instance:
    """Two-route, two-station layout where battery/time never bind, so every coupled move type
    is guaranteed feasible (no reliance on a real benchmark instance "happening" to allow one)."""
    nodes = {
        "D0": _node("D0", "depot", 0.0, due=10_000.0),
        "C1": _node("C1", "customer", 10.0, demand=1.0),
        "C2": _node("C2", "customer", 20.0, demand=1.0),
        "C3": _node("C3", "customer", 30.0, demand=1.0),
        "C4": _node("C4", "customer", 40.0, demand=1.0),
        "F1": _node("F1", "station", 15.0),
        "F2": _node("F2", "station", 35.0),
    }
    vehicle = Vehicle(freight_capacity=1_000.0, battery_capacity=1_000.0, initial_soc=1_000.0,
                      consumption_rate=0.1, velocity=1.0, inverse_refuel_rate=0.1)
    return Instance("TINY_GENEROUS", "synthetic", nodes, "D0", ("C1", "C2", "C3", "C4"), ("F1", "F2"),
                    vehicle, 10_000.0, {})


def _generous_solution(instance: Instance) -> Solution:
    route0 = propagate_route(instance, ("D0", "C1", "F1", "C2", "D0"), vehicle_index=0)
    route1 = propagate_route(instance, ("D0", "C3", "C4", "D0"), vehicle_index=1)
    return Solution((route0, route1))


def _battery_instance(
    battery_capacity: float, f1_x: float, f2_x: float, customer_x: float, customer_id: str = "C1",
) -> Instance:
    """Single-customer, two-station layout where feasibility is controlled purely by battery
    capacity vs. geometry, so the number of charging stops a feasible route needs is deterministic."""
    nodes = {
        "D0": _node("D0", "depot", 0.0, due=10_000.0),
        customer_id: _node(customer_id, "customer", customer_x, demand=1.0),
        "F1": _node("F1", "station", f1_x),
        "F2": _node("F2", "station", f2_x),
    }
    vehicle = Vehicle(freight_capacity=100.0, battery_capacity=battery_capacity, initial_soc=battery_capacity,
                      consumption_rate=1.0, velocity=1.0, inverse_refuel_rate=0.1)
    return Instance("TINY_TIGHT", "synthetic", nodes, "D0", (customer_id,), ("F1", "F2"),
                    vehicle, 10_000.0, {})


def test_generous_fixture_guarantees_all_four_move_types_are_feasible() -> None:
    instance = _generous_instance()
    solution = _generous_solution(instance)
    moves = enumerate_moves(instance, solution, max_per_type=30)
    present = {m.move_type for m in moves}
    assert present == set(MoveType)
    for kind in MoveType:
        candidates = [m for m in moves if m.move_type is kind]
        assert any(apply_move(instance, solution, m) is not None for m in candidates), kind


def test_one_station_reconstruction_needs_and_uses_exactly_one_charging_stop() -> None:
    """Direct D0->C1->D0 (50 units) exceeds the 49-unit battery, so a single recharge near the
    depot is both necessary and sufficient for this geometry."""
    instance = _battery_instance(battery_capacity=49.0, f1_x=2.0, f2_x=200.0, customer_x=25.0)
    route = reconstruct_route_charging(instance, ("C1",), vehicle_index=0)
    assert route is not None
    station_stops = [n for n in route.node_ids if n in instance.station_ids]
    assert station_stops == ["F1"]
    assert evaluate_feasibility(instance, Solution((route,))).feasible


def test_two_station_reconstruction_needs_two_charging_stops() -> None:
    """C2 is far enough (100-unit round trip) that a single recharge cannot cover both the
    outbound and return leg with this battery, forcing the beam search to schedule two stops."""
    instance = _battery_instance(battery_capacity=45.0, f1_x=5.0, f2_x=45.0, customer_x=50.0, customer_id="C2")
    config = ChargingReconstructionConfig(max_inserted_stations_per_route=6, max_expansions=400)
    route = reconstruct_route_charging(instance, ("C2",), vehicle_index=0, config=config)
    assert route is not None
    station_stops = [n for n in route.node_ids if n in instance.station_ids]
    assert len(station_stops) == 2
    assert evaluate_feasibility(instance, Solution((route,))).feasible


def test_reconstruct_route_charging_empty_customers_returns_none() -> None:
    instance = _generous_instance()
    assert reconstruct_route_charging(instance, (), vehicle_index=0) is None


def test_compute_features_calls_apply_move_exactly_once() -> None:
    """compute_features must not re-derive the after-state more than once per move (it is the
    hot path evaluated for every enumerated candidate)."""
    instance = _generous_instance()
    solution = _generous_solution(instance)
    moves = enumerate_moves(instance, solution, max_per_type=10)
    feasible_move = next(m for m in moves if apply_move(instance, solution, m) is not None)
    real_apply_move = features_module.apply_move
    with patch.object(features_module, "apply_move", wraps=real_apply_move) as mocked:
        compute_features(instance, solution, feasible_move)
        assert mocked.call_count == 1


def test_compute_features_returns_exact_feature_catalogue() -> None:
    instance = load_instance(SCHNEIDER / "c101C5.txt")
    solution = construct_initial_solution(instance).solution
    moves = enumerate_moves(instance, solution, max_per_type=10)
    feasible_moves = [m for m in moves if apply_move(instance, solution, m) is not None]
    assert feasible_moves
    features = compute_features(instance, solution, feasible_moves[0])
    assert set(features) == set(FEATURE_NAMES)
    assert all(isinstance(v, float) for v in features.values())
