"""Deterministic EVRPTW feasibility verification."""

from __future__ import annotations

from evocharge.distances.matrix import DistanceMatrix
from evocharge.distances.provider import DistanceProvider, default_provider
from evocharge.domain.charging import ChargingModel, default_charging_model
from evocharge.domain.instance import Instance
from evocharge.domain.objective import ObjectiveVector
from evocharge.domain.route import Route
from evocharge.domain.solution import Solution
from evocharge.domain.violations import FeasibilityReport
from evocharge.solver.propagation import propagate_route


def _ensure_scheduled(
    instance: Instance,
    route: Route,
    provider: DistanceProvider,
    charging_model: ChargingModel,
) -> Route:
    if route.schedule and len(route.schedule) == len(route.node_ids):
        return route
    return propagate_route(
        instance,
        route.node_ids,
        vehicle_index=route.vehicle_index,
        provider=provider,
        charging_model=charging_model,
    )


def evaluate_feasibility(
    instance: Instance,
    solution: Solution,
    *,
    provider: DistanceProvider | None = None,
    charging_model: ChargingModel | None = None,
    repropagate: bool = True,
) -> FeasibilityReport:
    """Return a typed feasibility report. Only this validator certifies feasibility."""
    provider = provider or default_provider()
    charging_model = charging_model or default_charging_model()
    matrix = DistanceMatrix(instance, provider)

    missing: list[str] = []
    duplicates: list[str] = []
    invalid_visits: list[dict] = []
    capacity: list[dict] = []
    time_windows: list[dict] = []
    battery: list[dict] = []
    charging: list[dict] = []
    station_policy: list[dict] = []
    depot: list[dict] = []
    unreachable: list[dict] = []
    warnings: list[str] = []

    served: list[str] = []
    customer_set = set(instance.customer_ids)

    scheduled_routes: list[Route] = []
    for route in solution.routes:
        scheduled = (
            _ensure_scheduled(instance, route, provider, charging_model)
            if repropagate
            else route
        )
        scheduled_routes.append(scheduled)

        if not scheduled.node_ids:
            depot.append({"route": scheduled.vehicle_index, "reason": "empty_route"})
            continue
        if scheduled.node_ids[0] != instance.depot_id:
            depot.append(
                {
                    "route": scheduled.vehicle_index,
                    "reason": "must_start_at_depot",
                    "got": scheduled.node_ids[0],
                }
            )
        if scheduled.node_ids[-1] != instance.depot_id:
            depot.append(
                {
                    "route": scheduled.vehicle_index,
                    "reason": "must_end_at_depot",
                    "got": scheduled.node_ids[-1],
                }
            )

        for node_id in scheduled.node_ids:
            if node_id not in instance.nodes:
                invalid_visits.append(
                    {"route": scheduled.vehicle_index, "node": node_id, "reason": "unknown_node"}
                )
                continue
            kind = instance.nodes[node_id].kind
            if kind == "customer":
                served.append(node_id)
            elif kind not in {"depot", "station"}:
                invalid_visits.append(
                    {"route": scheduled.vehicle_index, "node": node_id, "reason": "invalid_kind"}
                )

        # Arc reachability
        for i in range(len(scheduled.node_ids) - 1):
            a, b = scheduled.node_ids[i], scheduled.node_ids[i + 1]
            arc = matrix.get(a, b)
            if not arc.reachable:
                unreachable.append(
                    {"route": scheduled.vehicle_index, "from": a, "to": b}
                )

        if not scheduled.schedule:
            warnings.append(f"route_{scheduled.vehicle_index}_missing_schedule")
            continue

        for stop in scheduled.schedule:
            node = instance.nodes.get(stop.node_id)
            if node is None:
                continue
            if stop.cumulative_load > instance.vehicle.freight_capacity + 1e-6:
                capacity.append(
                    {
                        "route": scheduled.vehicle_index,
                        "node": stop.node_id,
                        "load": stop.cumulative_load,
                        "capacity": instance.vehicle.freight_capacity,
                    }
                )
            if node.kind == "customer" and stop.service_start > node.due_time + 1e-6:
                time_windows.append(
                    {
                        "route": scheduled.vehicle_index,
                        "node": stop.node_id,
                        "service_start": stop.service_start,
                        "due_time": node.due_time,
                    }
                )
            if stop.battery_on_arrival < -1e-6:
                battery.append(
                    {
                        "route": scheduled.vehicle_index,
                        "node": stop.node_id,
                        "battery_on_arrival": stop.battery_on_arrival,
                        "reason": "negative_on_arrival",
                    }
                )
            if stop.battery_on_departure < -1e-6:
                battery.append(
                    {
                        "route": scheduled.vehicle_index,
                        "node": stop.node_id,
                        "battery_on_departure": stop.battery_on_departure,
                        "reason": "negative_on_departure",
                    }
                )
            if stop.battery_on_departure > instance.vehicle.battery_capacity + 1e-6:
                battery.append(
                    {
                        "route": scheduled.vehicle_index,
                        "node": stop.node_id,
                        "battery_on_departure": stop.battery_on_departure,
                        "reason": "exceeds_capacity",
                    }
                )
            if node.kind == "station":
                errs = charging_model.validate_decision(
                    instance.vehicle,
                    stop.battery_on_arrival,
                    stop.energy_charged,
                )
                for err in errs:
                    charging.append(
                        {
                            "route": scheduled.vehicle_index,
                            "node": stop.node_id,
                            "reason": err,
                        }
                    )

        # Terminal SOC
        last = scheduled.schedule[-1]
        if last.battery_on_departure < instance.vehicle.terminal_soc_min - 1e-6:
            battery.append(
                {
                    "route": scheduled.vehicle_index,
                    "node": last.node_id,
                    "battery_on_departure": last.battery_on_departure,
                    "reason": "terminal_soc",
                }
            )

    # Customer coverage
    counts: dict[str, int] = {}
    for cid in served:
        counts[cid] = counts.get(cid, 0) + 1
    for cid in instance.customer_ids:
        c = counts.get(cid, 0)
        if c == 0:
            missing.append(cid)
        elif c > 1:
            duplicates.append(cid)
    for cid, _c in counts.items():
        if cid not in customer_set:
            invalid_visits.append({"node": cid, "reason": "non_customer_marked_served"})

    # Station policy: S0 colocated with depot is allowed; no further restriction claimed.
    _ = station_policy

    report = FeasibilityReport(
        feasible=False,
        missing_customers=missing,
        duplicate_customers=duplicates,
        invalid_node_visits=invalid_visits,
        capacity_violations=capacity,
        time_window_violations=time_windows,
        battery_violations=battery,
        charging_violations=charging,
        station_policy_violations=station_policy,
        depot_violations=depot,
        unreachable_arcs=unreachable,
        numerical_warnings=warnings,
    )
    report.feasible = report.violation_count == 0
    return report


def evaluate_objective(
    instance: Instance,
    solution: Solution,
    report: FeasibilityReport | None = None,
    *,
    provider: DistanceProvider | None = None,
) -> ObjectiveVector:
    report = report or evaluate_feasibility(instance, solution, provider=provider)
    provider = provider or default_provider()
    matrix = DistanceMatrix(instance, provider)

    total_distance = 0.0
    total_travel = 0.0
    total_charge = 0.0
    for route in solution.routes:
        scheduled = route
        if not route.schedule:
            scheduled = propagate_route(instance, route.node_ids, vehicle_index=route.vehicle_index)
        for i in range(len(scheduled.node_ids) - 1):
            arc = matrix.get(scheduled.node_ids[i], scheduled.node_ids[i + 1])
            total_distance += arc.distance
            total_travel += arc.travel_time
        for stop in scheduled.schedule:
            total_charge += stop.charging_duration

    return ObjectiveVector(
        infeasibility_count=report.violation_count,
        unserved_customers=len(report.missing_customers),
        vehicles_used=len(solution.routes),
        total_primary_cost=total_distance,
        total_distance=total_distance,
        total_travel_time=total_travel,
        total_charging_time=total_charge,
    )
