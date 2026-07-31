"""Route-level numerical diagnostics."""

from __future__ import annotations

from typing import Any

from evocharge.distances.matrix import DistanceMatrix
from evocharge.domain.instance import Instance
from evocharge.domain.route import Route
from evocharge.solver.route_utils import customer_sequence_of


def _quantiles(values: list[float]) -> list[float]:
    if not values:
        return []
    xs = sorted(values)
    n = len(xs)

    def q(p: float) -> float:
        if n == 1:
            return xs[0]
        idx = p * (n - 1)
        lo = int(idx)
        hi = min(n - 1, lo + 1)
        frac = idx - lo
        return xs[lo] * (1 - frac) + xs[hi] * frac

    return [q(0.0), q(0.25), q(0.5), q(0.75), q(1.0)]


def route_features(instance: Instance, route: Route) -> dict[str, Any]:
    matrix = DistanceMatrix(instance)
    customers = customer_sequence_of(route, instance)
    stations = [nid for nid in route.node_ids if nid in set(instance.station_ids)]
    distance = route.schedule[-1].traveled_distance if route.schedule else 0.0
    duration = route.schedule[-1].departure_time if route.schedule else 0.0
    load = max((s.cumulative_load for s in route.schedule), default=0.0)
    cap = instance.vehicle.freight_capacity
    waiting = sum(s.waiting_time for s in route.schedule)
    tw_slacks = [
        s.time_slack for s in route.schedule if s.node_id in set(instance.customer_ids)
    ]
    energy_slacks = [s.energy_slack for s in route.schedule]
    charge_time = sum(s.charging_duration for s in route.schedule)
    charge_stops = sum(1 for s in route.schedule if s.energy_charged > 1e-9)

    # Charging detour: compare customer-only path distance vs actual
    cust_path = (instance.depot_id, *customers, instance.depot_id)
    cust_dist = 0.0
    for a, b in zip(cust_path, cust_path[1:], strict=False):
        cust_dist += matrix.get(a, b).distance
    detour = max(0.0, distance - cust_dist)
    detour_ratio = detour / distance if distance > 1e-9 else 0.0

    station_counts: dict[str, int] = {}
    for sid in stations:
        station_counts[sid] = station_counts.get(sid, 0) + 1
    concentration = (
        max(station_counts.values()) / sum(station_counts.values())
        if station_counts
        else 0.0
    )
    dependency = 1.0 if len(station_counts) == 1 and charge_stops > 0 else (
        (max(station_counts.values()) / charge_stops) if charge_stops else 0.0
    )

    return {
        "n_customers": len(customers),
        "n_stations": len(stations),
        "distance": distance,
        "duration": duration,
        "capacity_utilization": (load / cap) if cap > 0 else 0.0,
        "waiting_time": waiting,
        "time_slack_min": min(tw_slacks) if tw_slacks else None,
        "time_slack_mean": (sum(tw_slacks) / len(tw_slacks)) if tw_slacks else None,
        "energy_slack_min": min(energy_slacks) if energy_slacks else None,
        "charging_stops": charge_stops,
        "charging_duration": charge_time,
        "charging_detour": detour,
        "charging_detour_ratio": detour_ratio,
        "station_use_concentration": concentration,
        "station_dependency": dependency,
        "customer_ids": list(customers),
        "node_ids": list(route.node_ids),
    }


def aggregate_route_features(features: list[dict[str, Any]]) -> dict[str, Any]:
    def col(name: str) -> list[float]:
        return [float(f[name]) for f in features if f.get(name) is not None]

    return {
        "n_routes": len(features),
        "distance_quantiles": _quantiles(col("distance")),
        "duration_quantiles": _quantiles(col("duration")),
        "capacity_utilization_quantiles": _quantiles(col("capacity_utilization")),
        "waiting_time_quantiles": _quantiles(col("waiting_time")),
        "charging_detour_ratio_quantiles": _quantiles(col("charging_detour_ratio")),
        "energy_slack_min_quantiles": _quantiles(col("energy_slack_min")),
        "station_dependency_quantiles": _quantiles(col("station_dependency")),
        "charging_stops_quantiles": _quantiles(col("charging_stops")),
    }
