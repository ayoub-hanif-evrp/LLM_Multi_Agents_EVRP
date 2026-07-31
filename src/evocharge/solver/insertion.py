"""Insertion cost evaluation and regret helpers."""

from __future__ import annotations

from dataclasses import dataclass

from evocharge.domain.instance import Instance
from evocharge.domain.route import Route
from evocharge.solver.charging_repair import ChargingRepairCache, RepairBounds, repair_charging
from evocharge.solver.profiling import Profiler
from evocharge.solver.route_utils import customer_sequence_of


@dataclass(frozen=True, slots=True)
class InsertionCandidate:
    route_index: int
    position: int
    customer_id: str
    cost_delta: float
    route: Route
    rejection: str | None = None


def evaluate_insertion(
    instance: Instance,
    route: Route,
    customer_id: str,
    position: int,
    *,
    vehicle_index: int,
    cache: ChargingRepairCache | None = None,
    bounds: RepairBounds | None = None,
    profiler: Profiler | None = None,
) -> InsertionCandidate:
    customers = list(customer_sequence_of(route, instance))
    if position < 0 or position > len(customers):
        return InsertionCandidate(
            route_index=vehicle_index,
            position=position,
            customer_id=customer_id,
            cost_delta=float("inf"),
            route=route,
            rejection="invalid_position",
        )
    if customer_id in customers:
        return InsertionCandidate(
            route_index=vehicle_index,
            position=position,
            customer_id=customer_id,
            cost_delta=float("inf"),
            route=route,
            rejection="duplicate_customer",
        )
    new_customers = tuple(customers[:position] + [customer_id] + customers[position:])
    demand = sum(instance.nodes[c].demand for c in new_customers)
    if demand > instance.vehicle.freight_capacity + 1e-6:
        return InsertionCandidate(
            route_index=vehicle_index,
            position=position,
            customer_id=customer_id,
            cost_delta=float("inf"),
            route=route,
            rejection="capacity",
        )
    repaired = repair_charging(
        instance,
        new_customers,
        vehicle_index=vehicle_index,
        cache=cache,
        bounds=bounds,
        profiler=profiler,
    )
    if repaired.status != "success" or repaired.route is None:
        return InsertionCandidate(
            route_index=vehicle_index,
            position=position,
            customer_id=customer_id,
            cost_delta=float("inf"),
            route=route,
            rejection=repaired.reason or "charging_repair_failed",
        )
    old_dist = route.schedule[-1].traveled_distance if route.schedule else 0.0
    new_dist = repaired.route.schedule[-1].traveled_distance
    return InsertionCandidate(
        route_index=vehicle_index,
        position=position,
        customer_id=customer_id,
        cost_delta=new_dist - old_dist,
        route=repaired.route,
        rejection=None,
    )


def best_insertions_for_customer(
    instance: Instance,
    routes: tuple[Route, ...],
    customer_id: str,
    *,
    cache: ChargingRepairCache | None = None,
    bounds: RepairBounds | None = None,
    profiler: Profiler | None = None,
    top_k: int = 3,
) -> list[InsertionCandidate]:
    cands: list[InsertionCandidate] = []
    for ridx, route in enumerate(routes):
        n = len(customer_sequence_of(route, instance))
        for pos in range(n + 1):
            cand = evaluate_insertion(
                instance,
                route,
                customer_id,
                pos,
                vehicle_index=ridx,
                cache=cache,
                bounds=bounds,
                profiler=profiler,
            )
            if cand.rejection is None:
                cands.append(cand)
    cands.sort(key=lambda c: c.cost_delta)
    return cands[:top_k]


def open_route_for_customer(
    instance: Instance,
    customer_id: str,
    *,
    vehicle_index: int,
    cache: ChargingRepairCache | None = None,
    bounds: RepairBounds | None = None,
    profiler: Profiler | None = None,
) -> InsertionCandidate:
    repaired = repair_charging(
        instance,
        (customer_id,),
        vehicle_index=vehicle_index,
        cache=cache,
        bounds=bounds,
        profiler=profiler,
    )
    if repaired.status != "success" or repaired.route is None:
        return InsertionCandidate(
            route_index=vehicle_index,
            position=0,
            customer_id=customer_id,
            cost_delta=float("inf"),
            route=Route(
                vehicle_index=vehicle_index,
                node_ids=(instance.depot_id, instance.depot_id),
            ),
            rejection=repaired.reason or "cannot_open_route",
        )
    dist = repaired.route.schedule[-1].traveled_distance
    return InsertionCandidate(
        route_index=vehicle_index,
        position=0,
        customer_id=customer_id,
        cost_delta=dist,
        route=repaired.route,
        rejection=None,
    )
