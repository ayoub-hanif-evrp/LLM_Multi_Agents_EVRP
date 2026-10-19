"""Bounded fleet packing for small multi-technology recharge instances.

Bezzi ``10-N10`` has four vehicles and several customers that do not fit on one
battery charge. Station insertion on the incumbent routes fails, and opening a
fifth route is forbidden. For at most twelve customers this module enumerates
short customer sequences, checks energy and duration with a restricted charge
set, then packs them into the available fleet. The exact recharge DP is run
only on the selected routes.
"""
from __future__ import annotations

import itertools
import time

from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.v2.bezzi_recharge import plan_bezzi_recharges
from evrptw_autolab.problem.v2.transport import energy_required, travel_time
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2, VehicleTypeV2

_MAX_CUSTOMERS = 12
_MAX_ROUTE_CUSTOMERS = 3


def pack_bezzi_fleet(
    spec: ProblemSpecV2,
    *,
    deadline: float | None = None,
) -> SolutionV2 | None:
    """Return a fleet-feasible solution, or None when no short cover is found."""
    if not spec.capabilities.multiple_charge_technologies or spec.capabilities.pickup_delivery:
        return None
    if spec.capabilities.heterogeneous_fleet or len(spec.vehicle_types) != 1:
        return None
    customers = [node.id for node in spec.nodes if node.kind == "customer"]
    if not customers or len(customers) > _MAX_CUSTOMERS or not spec.depot_ids:
        return None
    vehicle = spec.vehicle_types[0]
    if vehicle.battery_capacity is None:
        return None
    limit = spec.fleet_availability.get(vehicle.type_id)
    if limit is None:
        return None
    fleet_limit = min(int(limit), len(customers))
    if fleet_limit <= 0:
        return None
    sequences = _candidate_sequences(spec, vehicle, customers, deadline=deadline)
    if not sequences:
        return None
    chosen = _pack_sequences(customers, sequences, fleet_limit)
    if chosen is None:
        return None
    routes: list[list[RouteStopV2]] = []
    for sequence in chosen:
        stops = [RouteStopV2(node_id=node_id, event="visit") for node_id in sequence]
        planned = plan_bezzi_recharges(spec, stops, vehicle, drop_idle_stations=False)
        if planned is None:
            return None
        routes.append(planned)
    solution = SolutionV2(
        routes=routes,
        vehicle_assignments=[vehicle.type_id] * len(routes),
        metadata={"bezzi_pack": True},
    )
    report = evaluate(spec, solution)
    if not report.feasible:
        return None
    return solution


def _candidate_sequences(
    spec: ProblemSpecV2,
    vehicle: VehicleTypeV2,
    customers: list[str],
    *,
    deadline: float | None,
) -> list[tuple[str, ...]]:
    depot = spec.depot_ids[0]
    stations = [node.id for node in spec.nodes if node.kind == "station"]
    found: list[tuple[str, ...]] = []
    sizes = range(1, min(_MAX_ROUTE_CUSTOMERS, len(customers)) + 1)
    for size in sizes:
        for subset in itertools.combinations(customers, size):
            if deadline is not None and time.monotonic() > deadline:
                return found
            orders = list(itertools.permutations(subset))
            bare: tuple[str, ...] | None = None
            for order in orders:
                sequence = (depot, *order, depot)
                if _sequence_fits(spec, vehicle, sequence):
                    bare = sequence
                    break
            if bare is not None:
                found.append(bare)
                continue
            covered: tuple[str, ...] | None = None
            for order in orders:
                base = [depot, *order, depot]
                for station in stations:
                    for gap in range(1, len(base)):
                        sequence = tuple(base[:gap] + [station] + base[gap:])
                        if _sequence_fits(spec, vehicle, sequence):
                            covered = sequence
                            break
                    if covered is not None:
                        break
                if covered is not None:
                    break
            if covered is not None:
                found.append(covered)
    return found


def _pack_sequences(
    customers: list[str],
    sequences: list[tuple[str, ...]],
    fleet_limit: int,
) -> list[tuple[str, ...]] | None:
    index = {customer: bit for bit, customer in enumerate(customers)}
    labeled: list[tuple[int, tuple[str, ...]]] = []
    for sequence in sequences:
        mask = 0
        for node_id in sequence:
            bit = index.get(node_id)
            if bit is not None:
                mask |= 1 << bit
        if mask:
            labeled.append((mask, sequence))
    full = (1 << len(customers)) - 1
    best = [fleet_limit + 1] * (full + 1)
    parent: list[tuple[int, tuple[str, ...]] | None] = [None] * (full + 1)
    best[0] = 0
    for mask in range(full + 1):
        used = best[mask]
        if used >= fleet_limit:
            continue
        for route_mask, sequence in labeled:
            if mask & route_mask:
                continue
            nxt = mask | route_mask
            if used + 1 < best[nxt]:
                best[nxt] = used + 1
                parent[nxt] = (mask, sequence)
    if best[full] > fleet_limit:
        return None
    chosen: list[tuple[str, ...]] = []
    mask = full
    while mask:
        previous = parent[mask]
        if previous is None:
            return None
        mask, sequence = previous
        chosen.append(sequence)
    return chosen


def _sequence_fits(spec: ProblemSpecV2, vehicle: VehicleTypeV2, node_ids: tuple[str, ...]) -> bool:
    """Energy, capacity, and duration check with a small explicit charge set."""
    nodes = [spec.node_map[node_id] for node_id in node_ids]
    demand = sum(node.demand for node in nodes if node.kind == "customer")
    if demand > float(vehicle.capacity) + 1e-6:
        return False
    battery_cap = vehicle.battery_capacity
    if battery_cap is None:
        return False
    capacity = int(round(float(battery_cap)))
    if capacity <= 0 or abs(float(battery_cap) - capacity) > 1e-6:
        return False
    techs: dict[str, dict[str, float]] = vehicle.metadata.get("charging_techs") or {}
    max_time = vehicle.metadata.get("max_travel_time")
    limit = None if max_time is None else float(max_time)
    leg_energy: list[int] = []
    leg_time: list[float] = []
    for left, right in zip(nodes, nodes[1:], strict=False):
        raw = energy_required(spec, left, right, vehicle)
        energy = int(round(raw))
        if abs(raw - energy) > 1e-4:
            return False
        leg_energy.append(energy)
        leg_time.append(travel_time(spec, left, right, vehicle))
    states: list[tuple[int, float]] = [(0, 0.0)]
    for index, node in enumerate(nodes):
        can_charge = index == 0 or node.kind == "station"
        rho = _fastest_rho(node.charge_technologies, techs, depot=index == 0) if can_charge else 0.0
        nxt: list[tuple[int, float]] = []
        for battery, clock in states:
            for delta in _charge_options(can_charge, capacity - battery, leg_energy[index:]):
                charged = battery + delta
                updated = clock + rho * delta + node.service_time
                if index == len(nodes) - 1:
                    if limit is None or updated <= limit + 1e-6:
                        return True
                    continue
                need = leg_energy[index]
                if charged < need:
                    continue
                nxt.append((charged - need, updated + leg_time[index]))
        states = _prune(nxt)
        if not states:
            return False
    return False


def _charge_options(can_charge: bool, room: int, upcoming: list[int]) -> tuple[int, ...]:
    if not can_charge or room < 0:
        return (0,)
    options = {0, room}
    needed = 0
    for leg in upcoming:
        needed += leg
        if 0 < needed <= room:
            options.add(needed)
        elif needed > room:
            break
    return tuple(options)


def _fastest_rho(
    technologies: tuple[str, ...],
    techs: dict[str, dict[str, float]],
    *,
    depot: bool,
) -> float:
    choices = list(technologies) or (["0"] if depot else [])
    rhos = [float(techs[str(tech)]["rho"]) for tech in choices if str(tech) in techs]
    if not rhos and depot and "0" in techs:
        rhos.append(float(techs["0"]["rho"]))
    return min(rhos) if rhos else 0.0


def _prune(states: list[tuple[int, float]]) -> list[tuple[int, float]]:
    states.sort(key=lambda item: (item[1], -item[0]))
    kept: list[tuple[int, float]] = []
    best_battery = -1
    for battery, clock in states:
        if battery > best_battery:
            kept.append((battery, clock))
            best_battery = battery
    return kept
