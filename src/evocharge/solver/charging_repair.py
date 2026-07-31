"""Deterministic charging-repair for fixed customer sequences (contract-gated)."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Literal

from evocharge.distances.matrix import DistanceMatrix
from evocharge.distances.provider import DistanceProvider, default_provider
from evocharge.domain.instance import Instance
from evocharge.domain.route import Route
from evocharge.reproducibility import hash_mapping
from evocharge.solver.profiling import Profiler
from evocharge.solver.propagation import propagate_route
from evocharge.solver.route_utils import build_and_check_route, strip_stations


@dataclass(frozen=True, slots=True)
class ChargingRepairResult:
    status: Literal["success", "failure"]
    route: Route | None
    customer_sequence: tuple[str, ...]
    station_pattern: tuple[str, ...]
    reason: str | None = None
    cache_hit: bool = False
    attempts: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RepairBounds:
    max_stations_between: int = 1
    max_station_candidates: int = 8
    max_attempts: int = 400
    timeout_seconds: float = 2.0
    enable_two_station: bool = False
    enable_single_station_scan: bool = True
    single_scan_max_positions: int = 40


class ChargingRepairCache:
    """LRU cache with hit/miss statistics; stores compact station patterns."""

    def __init__(self, max_entries: int = 10_000) -> None:
        self.max_entries = max_entries
        self._store: OrderedDict[str, ChargingRepairResult] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> ChargingRepairResult | None:
        hit = self._store.get(key)
        if hit is None:
            self.misses += 1
            return None
        self.hits += 1
        self._store.move_to_end(key)
        return ChargingRepairResult(
            status=hit.status,
            route=hit.route,
            customer_sequence=hit.customer_sequence,
            station_pattern=hit.station_pattern,
            reason=hit.reason,
            cache_hit=True,
            attempts=hit.attempts,
            metadata=dict(hit.metadata),
        )

    def put(self, key: str, value: ChargingRepairResult) -> None:
        # Store without heavy schedule to save memory when possible:
        # keep node_ids via route if present (schedule rebuilt on hit).
        compact_route = None
        if value.route is not None:
            compact_route = Route(
                vehicle_index=value.route.vehicle_index,
                node_ids=value.route.node_ids,
                schedule=(),
                metadata={},
            )
        compact = ChargingRepairResult(
            status=value.status,
            route=compact_route,
            customer_sequence=value.customer_sequence,
            station_pattern=value.station_pattern,
            reason=value.reason,
            cache_hit=False,
            attempts=value.attempts,
            metadata=dict(value.metadata),
        )
        self._store[key] = compact
        self._store.move_to_end(key)
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)

    def stats(self) -> dict[str, Any]:
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "entries": len(self._store),
            "hit_rate": (self.hits / total) if total else 0.0,
        }


def cache_key_for_sequence(
    instance: Instance,
    customer_sequence: tuple[str, ...],
    *,
    bounds: RepairBounds,
) -> str:
    vehicle = instance.vehicle
    payload = {
        "customers": list(customer_sequence),
        "stations": list(instance.station_ids),
        "Q": vehicle.battery_capacity,
        "C": vehicle.freight_capacity,
        "r": vehicle.consumption_rate,
        "v": vehicle.velocity,
        "g": vehicle.inverse_refuel_rate,
        "gv": vehicle.charging_speed,
        "initial_soc": vehicle.initial_soc,
        "policy": "provisional_full_recharge_at_stations",
        "bounds": {
            "max_stations_between": bounds.max_stations_between,
            "max_station_candidates": bounds.max_station_candidates,
            "enable_two_station": bounds.enable_two_station,
            "enable_single_station_scan": bounds.enable_single_station_scan,
        },
        "dataset": instance.dataset_name,
    }
    return hash_mapping(payload)


def _skeleton(instance: Instance, customer_sequence: tuple[str, ...]) -> tuple[str, ...]:
    return (instance.depot_id, *customer_sequence, instance.depot_id)


def _station_candidates(instance: Instance) -> tuple[str, ...]:
    return tuple(instance.station_ids)


def _try_insertions_between(
    instance: Instance,
    left: str,
    right: str,
    matrix: DistanceMatrix,
    *,
    bounds: RepairBounds,
) -> list[tuple[str, ...]]:
    options: list[tuple[str, ...]] = [()]
    stations = _station_candidates(instance)
    if bounds.max_stations_between <= 0 or not stations:
        return options

    scored: list[tuple[float, str]] = []
    for sid in stations:
        detour = matrix.get(left, sid).distance + matrix.get(sid, right).distance
        scored.append((detour, sid))
    scored.sort()
    top = scored[: bounds.max_station_candidates]
    for _, sid in top:
        options.append((sid,))

    if bounds.enable_two_station and bounds.max_stations_between >= 2:
        top_ids = [s for _, s in top[: min(4, len(top))]]
        for a in top_ids:
            for b in top_ids:
                if a != b:
                    options.append((a, b))
    return options


def _budget_ok(attempts: int, t0: float, bounds: RepairBounds) -> bool:
    if attempts >= bounds.max_attempts:
        return False
    if (time.perf_counter() - t0) >= bounds.timeout_seconds:
        return False
    return True


def repair_charging(
    instance: Instance,
    node_or_customer_sequence: tuple[str, ...],
    *,
    vehicle_index: int = 0,
    max_stations_between: int | None = None,
    bounds: RepairBounds | None = None,
    cache: ChargingRepairCache | None = None,
    provider: DistanceProvider | None = None,
    profiler: Profiler | None = None,
) -> ChargingRepairResult:
    """Repair charging for a fixed customer order under bounded search."""
    bounds = bounds or RepairBounds(
        max_stations_between=max_stations_between
        if max_stations_between is not None
        else 1
    )
    if max_stations_between is not None:
        bounds.max_stations_between = max_stations_between

    def _run() -> ChargingRepairResult:
        return _repair_charging_impl(
            instance,
            node_or_customer_sequence,
            vehicle_index=vehicle_index,
            bounds=bounds,
            cache=cache,
            provider=provider,
        )

    if profiler is not None:
        with profiler.section("charging_repair"):
            return _run()
    return _run()


def _repair_charging_impl(
    instance: Instance,
    node_or_customer_sequence: tuple[str, ...],
    *,
    vehicle_index: int,
    bounds: RepairBounds,
    cache: ChargingRepairCache | None,
    provider: DistanceProvider | None,
) -> ChargingRepairResult:
    provider = provider or default_provider()
    matrix = DistanceMatrix(instance, provider)
    customers = tuple(
        nid
        for nid in strip_stations(node_or_customer_sequence, instance)
        if nid in set(instance.customer_ids)
    )
    key = cache_key_for_sequence(instance, customers, bounds=bounds)
    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            if cached.status == "success" and cached.route is not None:
                route = propagate_route(
                    instance,
                    cached.route.node_ids,
                    vehicle_index=vehicle_index,
                    provider=provider,
                )
                return ChargingRepairResult(
                    status="success",
                    route=route,
                    customer_sequence=customers,
                    station_pattern=cached.station_pattern,
                    reason=cached.reason,
                    cache_hit=True,
                    attempts=cached.attempts,
                    metadata={**cached.metadata, "from_cache": True},
                )
            return cached

    attempts = 0
    t0 = time.perf_counter()
    skeleton = _skeleton(instance, customers)

    attempts += 1
    direct = build_and_check_route(instance, skeleton, vehicle_index=vehicle_index)
    if direct is not None:
        result = ChargingRepairResult(
            status="success",
            route=direct,
            customer_sequence=customers,
            station_pattern=(),
            attempts=attempts,
            metadata={"method": "no_stations"},
        )
        if cache is not None:
            cache.put(key, result)
        return result

    built: list[str] = [instance.depot_id]
    for nxt in list(customers) + [instance.depot_id]:
        if not _budget_ok(attempts, t0, bounds):
            result = ChargingRepairResult(
                status="failure",
                route=None,
                customer_sequence=customers,
                station_pattern=(),
                reason="charging_repair_timeout",
                attempts=attempts,
                metadata={"failed_at": nxt, "prefix": list(built)},
            )
            if cache is not None:
                cache.put(key, result)
            return result

        placed = False
        options = _try_insertions_between(
            instance, built[-1], nxt, matrix, bounds=bounds
        )
        for stations in options:
            if not _budget_ok(attempts, t0, bounds):
                break
            attempts += 1
            candidate = tuple(built + list(stations) + [nxt])
            if nxt != instance.depot_id:
                route = propagate_route(
                    instance, candidate, vehicle_index=vehicle_index, provider=provider
                )
                ok = True
                for stop in route.schedule:
                    node = instance.nodes[stop.node_id]
                    if stop.battery_on_arrival < -1e-6 or stop.battery_on_departure < -1e-6:
                        ok = False
                        break
                    if node.kind == "customer" and stop.service_start > node.due_time + 1e-6:
                        ok = False
                        break
                    if stop.cumulative_load > instance.vehicle.freight_capacity + 1e-6:
                        ok = False
                        break
                if not ok:
                    continue
                built = list(candidate)
                placed = True
                break
            checked = build_and_check_route(
                instance, candidate, vehicle_index=vehicle_index
            )
            if checked is not None:
                station_pattern = tuple(
                    nid for nid in checked.node_ids if nid in set(instance.station_ids)
                )
                result = ChargingRepairResult(
                    status="success",
                    route=checked,
                    customer_sequence=customers,
                    station_pattern=station_pattern,
                    attempts=attempts,
                    metadata={"method": "greedy_forward"},
                )
                if cache is not None:
                    cache.put(key, result)
                return result
        if not placed and nxt != instance.depot_id:
            result = ChargingRepairResult(
                status="failure",
                route=None,
                customer_sequence=customers,
                station_pattern=(),
                reason="cannot_reach_next_with_supported_station_insertions",
                attempts=attempts,
                metadata={"failed_at": nxt, "prefix": list(built)},
            )
            if cache is not None:
                cache.put(key, result)
            return result

    if bounds.enable_single_station_scan:
        stations = _station_candidates(instance)
        positions = list(range(1, len(skeleton)))
        if len(positions) > bounds.single_scan_max_positions:
            # Sample evenly across the route for observability/bounds
            step = max(1, len(positions) // bounds.single_scan_max_positions)
            positions = positions[::step][: bounds.single_scan_max_positions]
        top_stations = list(stations)[: bounds.max_station_candidates]
        for i in positions:
            for sid in top_stations:
                if not _budget_ok(attempts, t0, bounds):
                    result = ChargingRepairResult(
                        status="failure",
                        route=None,
                        customer_sequence=customers,
                        station_pattern=(),
                        reason="charging_repair_timeout",
                        attempts=attempts,
                        metadata={"method": "single_station_scan"},
                    )
                    if cache is not None:
                        cache.put(key, result)
                    return result
                attempts += 1
                seq = skeleton[:i] + (sid,) + skeleton[i:]
                checked = build_and_check_route(
                    instance, seq, vehicle_index=vehicle_index
                )
                if checked is not None:
                    result = ChargingRepairResult(
                        status="success",
                        route=checked,
                        customer_sequence=customers,
                        station_pattern=(sid,),
                        attempts=attempts,
                        metadata={"method": "single_station_scan"},
                    )
                    if cache is not None:
                        cache.put(key, result)
                    return result

    reason = (
        "charging_repair_timeout"
        if not _budget_ok(attempts, t0, bounds)
        else "no_feasible_station_pattern_in_scope"
    )
    result = ChargingRepairResult(
        status="failure",
        route=None,
        customer_sequence=customers,
        station_pattern=(),
        reason=reason,
        attempts=attempts,
        metadata={"method": "exhausted"},
    )
    if cache is not None:
        cache.put(key, result)
    return result
