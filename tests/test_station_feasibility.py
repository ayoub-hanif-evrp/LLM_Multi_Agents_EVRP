"""Station scores rank survivors. They do not decide feasibility."""
from __future__ import annotations

from evrptw_autolab.backbone.local_search import merge_routes_improve
from evrptw_autolab.backbone.nonlinear_charge import optimize_route_partial_charges
from evrptw_autolab.backbone.station_filter import rank_station_candidates
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.components.expressions import wrap_expression
from evrptw_autolab.components.loader import load_bundle
from evrptw_autolab.problem.v2.features import (
    FEATURE_SCHEMA_V2,
    FEATURE_SCHEMA_VERSION,
    STATION_FEATURES_V1,
    STATION_FEATURES_V2,
    battery_argument_for_schema,
    station_feature_record,
)
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    RouteStopV2,
    SolutionV2,
    VehicleTypeV2,
)

RECORDED_STATION = "max(0, min(1, (battery_arrival - 0.2) * 5))"


def _spec(
    nodes: list[NodeV2],
    *,
    battery: float = 20.0,
    partial: bool = True,
    nonlinear: bool = False,
    max_travel: float | None = None,
    metadata: dict | None = None,
) -> tuple[ProblemSpecV2, VehicleTypeV2]:
    vehicle = VehicleTypeV2(
        type_id="EV",
        capacity=100.0,
        battery_capacity=battery,
        consumption_rate=1.0,
        velocity=1.0,
        is_electric=True,
        metadata={} if max_travel is None else {"max_travel_time": max_travel},
    )
    spec = ProblemSpecV2(
        instance_id="station-filter",
        family="synthetic",
        capabilities=CapabilityFlags(
            battery=True,
            partial_recharge=partial,
            full_recharge=not partial,
            nonlinear_charging=nonlinear,
            euclidean_distances=True,
            max_route_duration=max_travel is not None,
            time_windows=True,
        ),
        nodes=tuple(nodes),
        vehicle_types=(vehicle,),
        depot_ids=("D",),
        objective="minimize_duration",
        metadata=dict(metadata or {}),
    )
    return spec, vehicle


def _policy(expression: str):
    source = wrap_expression("station_score", expression)
    bundle, errors = load_bundle(
        {
            "insertion_score": wrap_expression("insertion_score", "delta_distance"),
            "station_score": source,
            "removal_priority": wrap_expression("removal_priority", "due_time"),
        }
    )
    assert not errors, errors
    bundle.station_trace = []  # type: ignore[attr-defined]
    return bundle


def _nodes_basic() -> list[NodeV2]:
    return [
        NodeV2("D", "depot", 0.0, 0.0),
        NodeV2("S_near", "station", 10.0, 0.0, recharging_rate=1.0),
        NodeV2("S_far", "station", 3.0, 0.0, recharging_rate=1.0),
        NodeV2("C", "customer", 4.0, 0.0, due_time=1.0e6),
    ]


def test_recorded_station_expression_is_constant_on_physical_energy() -> None:
    """The 0.2 threshold saturates once battery_arrival is above 0.4 energy units."""
    policy = _policy(RECORDED_STATION)
    score = policy.station_score
    assert score(1.0, 0.0, 1.0) == 0.0
    assert score(1.0, 0.2, 1.0) == 0.0
    assert score(5.0, 16000.0, 1.0) == 1.0
    assert score(0.1, 16000.0, 1.0) == score(1000.0, 16000.0, 1.0)
    assert STATION_FEATURES_V1["battery_arrival"]["range"] == "physical energy, not [0, 1]"
    assert STATION_FEATURES_V1["energy_slack_ratio"]["passed_to_scorer"] == "false"
    assert FEATURE_SCHEMA_VERSION == "2026-10-18.v1"


def test_score_cannot_select_an_unreachable_station() -> None:
    spec, vehicle = _spec(_nodes_basic(), battery=20.0, partial=False)
    # Lower is better, so -detour prefers the nearer station. That station is 10 energy away.
    policy = _policy("-1.0 * detour")
    choice, decisions = rank_station_candidates(
        spec, "D", "C", vehicle, battery_arrival=4.0, policy=policy
    )
    assert choice is not None and choice.station_id == "S_far"
    reasons = {item.station_id: item.reason for item in decisions}
    assert reasons["S_near"] == "unreachable"
    assert policy.call_counts["station_score"] == 1
    assert policy.station_trace[0]["reason"] == "ok"


def test_reachable_station_that_cannot_cover_the_next_leg_is_rejected() -> None:
    nodes = [
        NodeV2("D", "depot", 0.0, 0.0),
        NodeV2("S", "station", 1.0, 0.0, recharging_rate=0.0),
        NodeV2("C", "customer", 30.0, 0.0, due_time=1.0e6),
    ]
    spec, vehicle = _spec(nodes, battery=10.0, partial=False)
    choice, decisions = rank_station_candidates(spec, "D", "C", vehicle, battery_arrival=5.0)
    assert choice is None
    assert decisions[0].reason == "cannot_leave"


def test_detour_that_misses_the_customer_window_is_rejected() -> None:
    nodes = [
        NodeV2("D", "depot", 0.0, 0.0),
        NodeV2("S", "station", 1.0, 0.0, recharging_rate=1.0),
        NodeV2("C", "customer", 2.0, 0.0, due_time=4.0),
    ]
    spec, vehicle = _spec(nodes, battery=20.0, partial=False)
    choice, decisions = rank_station_candidates(
        spec, "D", "C", vehicle, battery_arrival=2.0, time_at_left=0.0, suffix_ids=["C", "D"]
    )
    assert choice is None
    assert decisions[0].reason == "window"


def test_partial_charge_is_kept_when_full_charge_misses_the_window() -> None:
    nodes = [
        NodeV2("D", "depot", 0.0, 0.0),
        NodeV2("S", "station", 1.0, 0.0, recharging_rate=1.0),
        NodeV2("C", "customer", 2.0, 0.0, due_time=8.0),
    ]
    spec, vehicle = _spec(nodes, battery=20.0, partial=True)
    choice, _decisions = rank_station_candidates(
        spec, "D", "C", vehicle, battery_arrival=2.0, suffix_ids=["C", "D"]
    )
    assert choice is not None
    # Arrival SoC is 1. Covering C and the depot takes 3, not a recharge to 20.
    # The full recharge lasts long enough to miss the due time of 8.
    assert choice.charge_energy == 3.0
    assert choice.reason == "ok"


def test_station_that_makes_the_route_exceed_max_duration_is_rejected() -> None:
    nodes = [
        NodeV2("D", "depot", 0.0, 0.0),
        NodeV2("S", "station", 1.0, 0.0, recharging_rate=1.0),
        NodeV2("C", "customer", 2.0, 0.0, due_time=1.0e6),
    ]
    spec, vehicle = _spec(nodes, battery=20.0, partial=False, max_travel=5.0)
    choice, decisions = rank_station_candidates(
        spec, "D", "C", vehicle, battery_arrival=2.0, suffix_ids=["C", "D"]
    )
    assert choice is None
    assert decisions[0].reason == "duration"


def test_missing_charging_curve_does_not_outrank_a_compatible_station() -> None:
    nodes = [
        NodeV2("D", "depot", 0.0, 0.0),
        NodeV2("S_bad", "station", 1.0, 0.0, charge_technologies=("missing",), recharging_rate=1.0),
        NodeV2("S_ok", "station", 3.0, 0.0, charge_technologies=("ok",), recharging_rate=1.0),
        NodeV2("C", "customer", 4.0, 0.0, due_time=1.0e6),
    ]
    curve = [{"battery_level": 0.0, "charging_time": 0.0}, {"battery_level": 20.0, "charging_time": 1.0}]
    spec, vehicle = _spec(
        nodes,
        battery=20.0,
        partial=False,
        nonlinear=True,
        metadata={"charging_functions": {"ok": curve}},
    )
    policy = _policy("-1.0 * detour")
    choice, decisions = rank_station_candidates(spec, "D", "C", vehicle, battery_arrival=20.0, policy=policy)
    assert choice is not None and choice.station_id == "S_ok"
    reasons = {item.station_id: item.reason for item in decisions}
    assert reasons["S_bad"] == "incompatible_charge"


def test_merged_route_over_max_duration_does_not_replace_a_feasible_incumbent() -> None:
    nodes = [
        NodeV2("D", "depot", 0.0, 0.0),
        NodeV2("C1", "customer", 6.0, 0.0, due_time=1.0e6),
        NodeV2("C2", "customer", 0.0, 6.0, due_time=1.0e6),
    ]
    spec, vehicle = _spec(nodes, battery=100.0, partial=False, max_travel=20.0)
    depot = RouteStopV2("D", vehicle_type_id="EV", event="depot")
    incumbent = SolutionV2(
        routes=[
            [depot, RouteStopV2("C1", vehicle_type_id="EV"), depot],
            [depot, RouteStopV2("C2", vehicle_type_id="EV"), depot],
        ],
        vehicle_assignments=["EV", "EV"],
    )
    before = evaluate(spec, incumbent)
    assert before.feasible, before.violations
    merged = SolutionV2(
        routes=[[
            depot,
            RouteStopV2("C1", vehicle_type_id="EV"),
            RouteStopV2("C2", vehicle_type_id="EV"),
            depot,
        ]],
        vehicle_assignments=["EV"],
    )
    merged_report = evaluate(spec, merged)
    assert any(item.family == "DURATION" for item in merged_report.violations)
    kept = merge_routes_improve(spec, incumbent)
    after = evaluate(spec, kept)
    assert after.feasible
    assert len(kept.routes) == 2
    assert vehicle.type_id == "EV"


def test_feature_scales_keep_v1_physical_and_v2_normalized() -> None:
    physical = battery_argument_for_schema(FEATURE_SCHEMA_VERSION, 8000.0, 16000.0)
    ratio = battery_argument_for_schema(FEATURE_SCHEMA_V2, 8000.0, 16000.0)
    assert physical == 8000.0
    assert ratio == 0.5
    record = station_feature_record(
        detour=10.0,
        battery_at_station=8000.0,
        battery_capacity=16000.0,
        energy_to_next=4000.0,
        direct_travel_time=1.0,
        detour_travel_time=1.4,
        charge_time=0.2,
        projected_completion=8.0,
        max_travel_time=10.0,
        technology="fast",
    )
    assert record["schema"] == FEATURE_SCHEMA_V2
    assert record["battery_arrival_ratio"] == 0.5
    assert record["energy_slack_ratio"] == 0.75
    assert record["route_duration_slack"] == 0.2
    assert abs(float(record["travel_time_detour"]) - 0.4) < 1e-9
    assert record["charge_time"] == 0.2
    assert record["station_technology"] == "fast"
    assert abs(float(record["incremental_objective_time"]) - 0.6) < 1e-9
    assert set(STATION_FEATURES_V2) >= {
        "battery_arrival_ratio",
        "energy_slack_ratio",
        "route_duration_slack",
        "travel_time_detour",
        "charge_time",
        "station_technology",
        "incremental_objective_time",
    }
    assert STATION_FEATURES_V1["battery_arrival"]["passed_to_scorer"] == "true"


def test_v2_schema_is_opt_in_and_does_not_rescale_v1() -> None:
    nodes = [
        NodeV2("D", "depot", 0.0, 0.0),
        NodeV2("S", "station", 1.0, 0.0, recharging_rate=1.0, charge_technologies=("fast",)),
        NodeV2("C", "customer", 2.0, 0.0, due_time=1.0e6),
    ]
    spec, vehicle = _spec(nodes, battery=16000.0, partial=False)
    seen: list[float] = []

    class _Policy:
        def __init__(self, schema: str) -> None:
            self.feature_schema = schema
            self.call_counts: dict[str, int] = {}

        def station_score(self, detour: float, battery_arrival: float, station_rate: float) -> float:
            seen.append(battery_arrival)
            return detour

    rank_station_candidates(spec, "D", "C", vehicle, battery_arrival=16000.0, policy=_Policy(FEATURE_SCHEMA_VERSION))
    assert seen[-1] > 1000.0
    rank_station_candidates(spec, "D", "C", vehicle, battery_arrival=16000.0, policy=_Policy(FEATURE_SCHEMA_V2))
    assert 0.0 <= seen[-1] <= 1.0


def test_fixed_route_partial_charge_beats_full_when_full_breaks_duration() -> None:
    curve = [
        {"battery_level": 0.0, "charging_time": 0.0},
        {"battery_level": 50.0, "charging_time": 1.0},
        {"battery_level": 100.0, "charging_time": 10.0},
    ]
    spec = ProblemSpecV2(
        instance_id="partial-vs-full",
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
            NodeV2("S", "station", 50, 0, charge_technologies=("fast",)),
            NodeV2("C", "customer", 70, 0),
        ),
        vehicle_types=(
            VehicleTypeV2(
                "EV",
                capacity=0.0,
                battery_capacity=100.0,
                consumption_rate=1.0,
                velocity=1.0,
                metadata={"charging_functions": {"fast": curve}, "max_travel_time": 148.0},
            ),
        ),
        depot_ids=("D",),
        metadata={"charging_functions": {"fast": curve}, "max_travel_time": 148.0},
    )
    bare = [
        RouteStopV2("D", event="depot"),
        RouteStopV2("S", event="charge", charge_technology="fast"),
        RouteStopV2("C", event="visit"),
        RouteStopV2("D", event="depot"),
    ]
    full = [
        RouteStopV2("D", event="depot"),
        RouteStopV2("S", event="charge", charge_technology="fast", target_soc=100.0),
        RouteStopV2("C", event="visit"),
        RouteStopV2("D", event="depot"),
    ]
    optimized = optimize_route_partial_charges(spec, bare, spec.vehicle_types[0])
    opt_report = evaluate(spec, SolutionV2(routes=[optimized], vehicle_assignments=["EV"]))
    full_report = evaluate(spec, SolutionV2(routes=[full], vehicle_assignments=["EV"]))
    assert opt_report.feasible, opt_report.violations
    assert not full_report.feasible
    assert opt_report.total_duration < full_report.total_duration
    assert float(optimized[1].target_soc or 0.0) < 100.0
