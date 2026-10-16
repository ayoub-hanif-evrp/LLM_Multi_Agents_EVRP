"""Canonical Bezzi recharge decisions: explicit amounts, removal, and cost."""
from __future__ import annotations

from evrptw_autolab.backbone.charge_completion import complete_solution_charges
from evrptw_autolab.problem.v2.bezzi_recharge import plan_bezzi_recharges
from evrptw_autolab.problem.v2.evaluator import evaluate_solution_v2
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    RouteStopV2,
    SolutionV2,
    VehicleTypeV2,
)


def _matrix(pairs: dict[tuple[str, str], int]) -> dict[str, dict[str, float]]:
    ids = sorted({node for arc in pairs for node in arc})
    out = {left: {right: 0.0 for right in ids} for left in ids}
    for (left, right), value in pairs.items():
        out[left][right] = float(value)
    return out


def _spec(energy: dict[tuple[str, str], int]) -> ProblemSpecV2:
    matrix = _matrix(energy)
    nodes = (
        NodeV2("D", "depot", 0, 0, charge_technologies=("0",)),
        NodeV2("C", "customer", 1, 0),
        NodeV2("S", "station", 2, 0, charge_technologies=("cheap", "pricey")),
        NodeV2("Z", "station", 0, 1, charge_technologies=("cheap",)),
    )
    return ProblemSpecV2(
        instance_id="bezzi_charge_micro",
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
                metadata={
                    "charging_techs": {
                        "0": {"gamma": 1.0, "rho": 0.0},
                        "cheap": {"gamma": 2.0, "rho": 0.0},
                        "pricey": {"gamma": 9.0, "rho": 0.0},
                    }
                },
            ),
        ),
        depot_ids=("D",),
        objective="minimize_recharge_cost",
        metadata={
            "fixed_recharge_cost": 3.0,
            "energy_matrix": matrix,
            "travel_time_matrix": matrix,
        },
    )


def _route(*node_ids: str) -> list[RouteStopV2]:
    stops: list[RouteStopV2] = []
    for index, node_id in enumerate(node_ids):
        if node_id == "D":
            event = "depot"
        elif node_id in {"S", "Z"}:
            event = "charge"
        else:
            event = "visit"
        del index
        stops.append(RouteStopV2(node_id, vehicle_type_id="EV", event=event))
    return stops


def _plan(spec: ProblemSpecV2, node_ids: tuple[str, ...], *, drop: bool = False) -> list[RouteStopV2]:
    vehicle = spec.vehicle_types[0]
    planned = plan_bezzi_recharges(spec, _route(*node_ids), vehicle, drop_idle_stations=drop)
    assert planned is not None
    return planned


def test_positive_recharge_uses_cheaper_station_technology() -> None:
    spec = _spec(
        {
            ("D", "C"): 4,
            ("C", "S"): 4,
            ("S", "D"): 4,
        }
    )
    planned = _plan(spec, ("D", "C", "S", "D"))
    depot, _customer, station, _end = planned
    assert depot.event == "depot"
    assert depot.charge_amount == 10.0
    assert depot.charge_technology == "0"
    assert station.event == "charge"
    assert station.charge_amount == 2.0
    assert station.charge_technology == "cheap"
    report = evaluate_solution_v2(
        spec, SolutionV2(routes=[planned], vehicle_assignments=["EV"])
    )
    assert report.feasible, [v.detail for v in report.violations]
    # Two operations: fixed 3*2 + depot 1*10 + cheap 2*2.
    assert report.objective == 20.0
    assert report.objective_components["recharge_cost"] == 20.0


def test_zero_recharge_station_is_explicit_and_not_a_charge_event() -> None:
    spec = _spec(
        {
            ("D", "Z"): 1,
            ("Z", "C"): 1,
            ("C", "D"): 6,
            ("D", "C"): 9,
        }
    )
    planned = _plan(spec, ("D", "Z", "C", "D"))
    station = planned[1]
    assert station.node_id == "Z"
    assert station.event == "visit"
    assert station.charge_amount == 0.0
    assert station.charge_technology is None
    report = evaluate_solution_v2(
        spec, SolutionV2(routes=[planned], vehicle_assignments=["EV"])
    )
    assert report.feasible, [v.detail for v in report.violations]
    assert not any("missing_charge" in v.detail for v in report.violations)
    # One depot operation: fixed 3 + gamma 1 * 8.
    assert report.objective == 11.0


def test_missing_charge_event_is_not_an_explicit_noop() -> None:
    spec = _spec(
        {
            ("D", "Z"): 1,
            ("Z", "C"): 1,
            ("C", "D"): 6,
        }
    )
    silent = [
        RouteStopV2("D", vehicle_type_id="EV", event="depot", charge_amount=8.0, charge_technology="0"),
        RouteStopV2("Z", vehicle_type_id="EV", event="charge"),
        RouteStopV2("C", vehicle_type_id="EV", event="visit"),
        RouteStopV2("D", vehicle_type_id="EV", event="depot"),
    ]
    missing = evaluate_solution_v2(spec, SolutionV2(routes=[silent], vehicle_assignments=["EV"]))
    assert any(v.detail.endswith("missing_charge_decision") for v in missing.violations)
    explicit = [
        RouteStopV2("D", vehicle_type_id="EV", event="depot", charge_amount=8.0, charge_technology="0"),
        RouteStopV2("Z", vehicle_type_id="EV", event="visit", charge_amount=0.0),
        RouteStopV2("C", vehicle_type_id="EV", event="visit"),
        RouteStopV2("D", vehicle_type_id="EV", event="depot"),
    ]
    kept = evaluate_solution_v2(spec, SolutionV2(routes=[explicit], vehicle_assignments=["EV"]))
    assert kept.feasible, [v.detail for v in kept.violations]


def test_mixed_zero_and_positive_recharge_visits() -> None:
    spec = _spec(
        {
            ("D", "Z"): 1,
            ("Z", "C"): 1,
            ("C", "S"): 6,
            ("S", "D"): 4,
            ("D", "C"): 9,
        }
    )
    planned = _plan(spec, ("D", "Z", "C", "S", "D"))
    by_id = {stop.node_id: stop for stop in planned}
    assert by_id["Z"].charge_amount == 0.0
    assert by_id["Z"].event == "visit"
    assert by_id["S"].event == "charge"
    assert by_id["S"].charge_amount == 2.0
    assert by_id["S"].charge_technology == "cheap"
    assert planned[0].charge_amount == 10.0
    assert planned[0].charge_technology == "0"


def test_incompatible_technology_is_rejected() -> None:
    spec = _spec({("D", "S"): 4, ("S", "D"): 4})
    route = [
        RouteStopV2("D", vehicle_type_id="EV", event="depot", charge_amount=4.0, charge_technology="0"),
        RouteStopV2(
            "S",
            vehicle_type_id="EV",
            event="charge",
            charge_amount=4.0,
            charge_technology="not-a-tech",
        ),
        RouteStopV2("D", vehicle_type_id="EV", event="depot"),
    ]
    report = evaluate_solution_v2(spec, SolutionV2(routes=[route], vehicle_assignments=["EV"]))
    assert any("incompatible_technology:not-a-tech" in v.detail for v in report.violations)


def test_idle_station_is_removed_when_the_shorter_route_stays_feasible() -> None:
    spec = _spec(
        {
            ("D", "Z"): 1,
            ("Z", "C"): 3,
            ("C", "D"): 4,
            ("D", "C"): 4,
        }
    )
    kept = _plan(spec, ("D", "Z", "C", "D"), drop=False)
    assert [stop.node_id for stop in kept] == ["D", "Z", "C", "D"]
    assert kept[1].charge_amount == 0.0
    removed = _plan(spec, ("D", "Z", "C", "D"), drop=True)
    assert [stop.node_id for stop in removed] == ["D", "C", "D"]
    report = evaluate_solution_v2(
        spec, SolutionV2(routes=[removed], vehicle_assignments=["EV"])
    )
    assert report.feasible
    # Direct route needs 8 energy at the depot: fixed 3 + 8.
    assert report.objective == 11.0


def test_idle_station_stays_when_removal_breaks_the_plan() -> None:
    spec = _spec(
        {
            ("D", "Z"): 1,
            ("Z", "C"): 1,
            ("C", "D"): 6,
            ("D", "C"): 9,
        }
    )
    planned = _plan(spec, ("D", "Z", "C", "D"), drop=True)
    assert [stop.node_id for stop in planned] == ["D", "Z", "C", "D"]
    assert planned[1].charge_amount == 0.0
    assert planned[1].event == "visit"


def test_charge_completion_reports_an_impossible_plan() -> None:
    spec = _spec({("D", "C"): 11, ("C", "D"): 1})
    raw = SolutionV2(routes=[_route("D", "C", "D")], vehicle_assignments=["EV"])
    out = complete_solution_charges(spec, raw)
    assert out.metadata["charge_completion"] == "bezzi_dp_failed"
    assert out.metadata["charge_completion_failed_routes"] == [0]
    assert all(stop.charge_amount is None for stop in out.routes[0])
    report = evaluate_solution_v2(spec, out)
    assert not report.feasible
