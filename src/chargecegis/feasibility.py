"""Single authoritative feasibility and objective evaluator."""
from __future__ import annotations

from chargecegis.charging import EPSILON, LinearFullRechargeModel
from chargecegis.problem import FeasibilityReport, Instance, ObjectiveVector, Solution
from chargecegis.propagation import arc_metrics, propagate_route


def evaluate_feasibility(instance: Instance, solution: Solution) -> FeasibilityReport:
    report = FeasibilityReport()
    served: list[str] = []
    model = LinearFullRechargeModel()
    for route in solution.routes:
        if not route.node_ids or route.node_ids[0] != instance.depot_id:
            report.depot_violations.append({"route": route.vehicle_index, "reason": "must_start_at_depot"})
        if not route.node_ids or route.node_ids[-1] != instance.depot_id:
            report.depot_violations.append({"route": route.vehicle_index, "reason": "must_end_at_depot"})
        try:
            scheduled = propagate_route(instance, route.node_ids, vehicle_index=route.vehicle_index)
        except (KeyError, ValueError) as error:
            report.invalid_node_visits.append({"route": route.vehicle_index, "reason": str(error)})
            continue
        for stop in scheduled.schedule:
            node = instance.nodes[stop.node_id]
            if node.kind == "customer":
                served.append(node.id)
                if stop.service_start > node.due_time + EPSILON:
                    report.time_window_violations.append({"node": node.id, "service_start": stop.service_start})
            if stop.cumulative_load > instance.vehicle.freight_capacity + EPSILON:
                report.capacity_violations.append({"node": node.id, "load": stop.cumulative_load})
            if stop.battery_on_arrival < -EPSILON or stop.battery_on_departure < -EPSILON:
                report.battery_violations.append({"node": node.id, "reason": "negative_battery"})
            if stop.battery_on_departure > instance.vehicle.battery_capacity + EPSILON:
                report.battery_violations.append({"node": node.id, "reason": "battery_capacity"})
            if node.kind == "station":
                for reason in model.validate_decision(instance.vehicle, stop.battery_on_arrival,
                                                      stop.energy_charged):
                    report.charging_violations.append({"node": node.id, "reason": reason})
        if scheduled.schedule and scheduled.schedule[-1].arrival_time > instance.depot.due_time + EPSILON:
            report.depot_violations.append({"route": route.vehicle_index, "reason": "depot_due_time"})
    counts = {customer: served.count(customer) for customer in instance.customer_ids}
    report.missing_customers = [cid for cid, count in counts.items() if count == 0]
    report.duplicate_customers = [cid for cid, count in counts.items() if count > 1]
    report.feasible = report.violation_count == 0
    return report


def evaluate_objective(instance: Instance, solution: Solution,
                       report: FeasibilityReport | None = None) -> ObjectiveVector:
    report = report or evaluate_feasibility(instance, solution)
    distance = travel = charging = 0.0
    for route in solution.routes:
        scheduled = propagate_route(instance, route.node_ids, vehicle_index=route.vehicle_index)
        for left, right in zip(route.node_ids, route.node_ids[1:]):
            arc = arc_metrics(instance, left, right)
            distance += arc.distance
            travel += arc.travel_time
        charging += sum(stop.charging_duration for stop in scheduled.schedule)
    return ObjectiveVector(report.violation_count, len(report.missing_customers), len(solution.routes),
                           distance, travel, charging)
