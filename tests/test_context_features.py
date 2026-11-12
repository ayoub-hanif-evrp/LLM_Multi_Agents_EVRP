"""Peak load must not cancel signed pickup-delivery demands."""

from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    RequestV2,
    RouteStopV2,
    SolutionV2,
    VehicleTypeV2,
)
from evrptw_autolab.transfer.context_features import search_context


def test_goeke_style_pair_has_nonzero_peak_utilization() -> None:
    spec = ProblemSpecV2(
        instance_id="pd_pair",
        family="goeke",
        capabilities=CapabilityFlags(
            pickup_delivery=True, time_windows=True, capacity=True, battery=True, euclidean_distances=True
        ),
        nodes=(
            NodeV2("D", "depot", 0.0, 0.0, due_time=1000.0),
            NodeV2("P", "pickup", 1.0, 0.0, demand=5.0, due_time=1000.0, partner_id="Q"),
            NodeV2("Q", "delivery", 2.0, 0.0, demand=-5.0, due_time=1000.0, partner_id="P"),
        ),
        vehicle_types=(
            VehicleTypeV2(
                "EV",
                capacity=10.0,
                battery_capacity=100.0,
                consumption_rate=0.1,
                velocity=1.0,
                metadata={"inverse_refuel_rate": 1.0},
            ),
        ),
        depot_ids=("D",),
        requests=(RequestV2("r1", "P", "Q", 5.0),),
    )
    solution = SolutionV2(
        routes=[
            [
                RouteStopV2("D", "EV", "depot"),
                RouteStopV2("P", "EV", "pickup"),
                RouteStopV2("Q", "EV", "delivery"),
                RouteStopV2("D", "EV", "depot"),
            ]
        ],
        vehicle_assignments=["EV"],
    )
    features = search_context(spec, solution)
    assert "instance_id" not in features
    assert features["route_utilization"] == 0.5
    assert features["peak_load_ratio"] == 0.5
