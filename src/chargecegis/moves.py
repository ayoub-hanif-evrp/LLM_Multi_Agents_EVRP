"""Deterministic catalogue of coupled customer and charging moves, plus removal-unit pooling
for equal-budget destroy/repair comparisons (see :mod:`chargecegis.alns`)."""
from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from .construction import (
    ChargingReconstructionConfig,
    _route_is_locally_feasible,
    reconstruct_route_charging,
)
from .feasibility import evaluate_feasibility
from .problem import Instance, Route, Solution
from .propagation import propagate_route

_DEFAULT_CONFIG = ChargingReconstructionConfig()


class MoveType(StrEnum):
    SEGMENT_RELOCATION = "SEGMENT_RELOCATION"
    TAIL_EXCHANGE = "TAIL_EXCHANGE"
    STATION_REPLACEMENT = "STATION_REPLACEMENT"
    STATION_REMOVAL = "STATION_REMOVAL"


@dataclass(frozen=True, slots=True)
class Move:
    move_type: MoveType
    route_i: int
    route_j: int | None = None
    indices: tuple[int, ...] = ()
    station_ids: tuple[str, ...] = ()
    segment: tuple[str, ...] = ()


def _is_customer(instance: Instance, node_id: str) -> bool:
    return node_id in instance.customer_ids


def move_hash(move: Move) -> str:
    """Stable content hash of a move's identity, independent of object identity."""
    payload = repr((
        move.move_type.value,
        move.route_i,
        move.route_j,
        move.indices,
        move.station_ids,
        move.segment,
    )).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def enumerate_moves(instance: Instance, solution: Solution, max_per_type: int = 20) -> list[Move]:
    """Enumerate a bounded, stable catalogue; route indices are solution positions."""
    result: list[Move] = []
    buckets: dict[MoveType, list[Move]] = {kind: [] for kind in MoveType}
    for i, route in enumerate(solution.routes):
        ids = route.node_ids
        customer_positions = [p for p, nid in enumerate(ids) if _is_customer(instance, nid)]
        for start in customer_positions:
            end = start
            while end + 1 < len(ids) and _is_customer(instance, ids[end + 1]):
                end += 1
                break  # bounded contiguous segments of one or two customers
            segment = ids[start:end + 1]
            for j, target in enumerate(solution.routes):
                for insert_at in range(1, max(1, len(target.node_ids))):
                    if i != j or not (start <= insert_at <= end + 1):
                        buckets[MoveType.SEGMENT_RELOCATION].append(
                            Move(MoveType.SEGMENT_RELOCATION, i, j, (start, end, insert_at), segment=segment)
                        )
        for cut_i in customer_positions:
            for j in range(i + 1, len(solution.routes)):
                for cut_j in [p for p, n in enumerate(solution.routes[j].node_ids) if _is_customer(instance, n)]:
                    buckets[MoveType.TAIL_EXCHANGE].append(
                        Move(MoveType.TAIL_EXCHANGE, i, j, (cut_i, cut_j))
                    )
        for pos, station in enumerate(ids):
            if station not in instance.station_ids:
                continue
            buckets[MoveType.STATION_REMOVAL].append(
                Move(MoveType.STATION_REMOVAL, i, indices=(pos,), station_ids=(station,))
            )
            for alternative in instance.station_ids:
                if alternative != station:
                    buckets[MoveType.STATION_REPLACEMENT].append(
                        Move(MoveType.STATION_REPLACEMENT, i, indices=(pos,), station_ids=(station, alternative))
                    )
    for kind in MoveType:
        result.extend(buckets[kind][:max_per_type])
    return result


def apply_move(
    instance: Instance,
    solution: Solution,
    move: Move,
    config: ChargingReconstructionConfig | None = None,
) -> Solution | None:
    """Apply a move, reconstruct charging on affected routes, and certify feasibility.

    Only routes touched by the move are rebuilt: customer-preserving sequences are derived for
    each affected route (stripping any now-obsolete stations), then re-charged via
    ``reconstruct_route_charging``. Station-only moves first try the minimal direct edit
    (propagate + local feasibility) before falling back to a full reconstruction. Routes left
    without customers are dropped and vehicle indices are renumbered densely from 0. Returns
    ``None`` if the move is structurally invalid, any affected route cannot be reconstructed
    feasibly, or the rebuilt solution fails full feasibility evaluation.
    """
    config = config or _DEFAULT_CONFIG
    n_routes = len(solution.routes)
    if not (0 <= move.route_i < n_routes) or (
        move.route_j is not None and not 0 <= move.route_j < n_routes
    ):
        return None
    seq = [route.node_ids for route in solution.routes]
    affected: set[int] = {move.route_i}
    try:
        if move.move_type is MoveType.SEGMENT_RELOCATION:
            start, end, insertion = move.indices
            target_index = move.route_j if move.route_j is not None else move.route_i
            segment = seq[move.route_i][start:end + 1]
            if not segment or any(not _is_customer(instance, node) for node in segment):
                return None
            origin = seq[move.route_i][:start] + seq[move.route_i][end + 1:]
            if target_index == move.route_i:
                position = insertion - len(segment) if insertion > end else insertion
                seq[move.route_i] = origin[:position] + segment + origin[position:]
            else:
                target = seq[target_index][:insertion] + segment + seq[target_index][insertion:]
                seq[move.route_i] = origin
                seq[target_index] = target
                affected.add(target_index)
        elif move.move_type is MoveType.TAIL_EXCHANGE:
            if move.route_j is None:
                return None
            cut_i, cut_j = move.indices
            left, right = seq[move.route_i], seq[move.route_j]
            seq[move.route_i] = left[:cut_i] + right[cut_j:]
            seq[move.route_j] = right[:cut_j] + left[cut_i:]
            affected.add(move.route_j)
        elif move.move_type is MoveType.STATION_REPLACEMENT:
            pos = move.indices[0]
            old, new = move.station_ids
            if seq[move.route_i][pos] != old or new not in instance.station_ids:
                return None
            seq[move.route_i] = seq[move.route_i][:pos] + (new,) + seq[move.route_i][pos + 1:]
        elif move.move_type is MoveType.STATION_REMOVAL:
            pos = move.indices[0]
            if seq[move.route_i][pos] not in instance.station_ids:
                return None
            seq[move.route_i] = seq[move.route_i][:pos] + seq[move.route_i][pos + 1:]
        else:
            return None
    except (IndexError, ValueError):
        return None

    is_station_only_move = move.move_type in (MoveType.STATION_REPLACEMENT, MoveType.STATION_REMOVAL)
    new_routes: list[Route] = []
    for index, route in enumerate(solution.routes):
        if index not in affected:
            new_routes.append(route)
            continue
        node_ids = seq[index]
        if not any(_is_customer(instance, nid) for nid in node_ids):
            continue  # route emptied of customers: drop it rather than force a reconstruction
        rebuilt: Route | None = None
        if is_station_only_move and index == move.route_i:
            try:
                direct = propagate_route(instance, node_ids, vehicle_index=route.vehicle_index)
            except (KeyError, ValueError):
                direct = None
            if direct is not None and _route_is_locally_feasible(instance, direct):
                rebuilt = direct
        if rebuilt is None:
            rebuilt = reconstruct_route_charging(
                instance, node_ids, vehicle_index=route.vehicle_index, config=config
            )
        if rebuilt is None:
            return None
        new_routes.append(rebuilt)

    if not new_routes:
        return None
    renumbered = tuple(replace(r, vehicle_index=i) for i, r in enumerate(new_routes))
    candidate = replace(solution, routes=renumbered)
    return candidate if evaluate_feasibility(instance, candidate).feasible else None


@dataclass(frozen=True, slots=True)
class RemovalUnit:
    """A contiguous customer segment on one route, candidate for equal-budget destroy/repair."""
    route_index: int
    start_customer_position: int  # index in node_ids
    end_customer_position: int
    customer_ids: tuple[str, ...]
    affected_station_ids: tuple[str, ...] = ()


def unit_hash(unit: RemovalUnit) -> str:
    """Stable content hash of a removal unit's identity, independent of object identity."""
    payload = repr((
        unit.route_index,
        unit.start_customer_position,
        unit.end_customer_position,
        unit.customer_ids,
        unit.affected_station_ids,
    )).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def enumerate_removal_units(
    instance: Instance, solution: Solution, *, max_segment_length: int = 3
) -> list[RemovalUnit]:
    """Enumerate contiguous customer segments (length 1..``max_segment_length``) on every route.

    "Contiguous" means adjacent entries in the route's customer-only order; any stations sitting
    between the segment's boundary customers (or immediately adjacent to them) are recorded as
    ``affected_station_ids`` since removing the segment may make them redundant.
    """
    units: list[RemovalUnit] = []
    for route_index, route in enumerate(solution.routes):
        ids = route.node_ids
        customer_positions = [p for p, nid in enumerate(ids) if _is_customer(instance, nid)]
        n = len(customer_positions)
        for i in range(n):
            for length in range(1, max_segment_length + 1):
                j = i + length - 1
                if j >= n:
                    break
                left_bound = customer_positions[i - 1] if i > 0 else -1
                right_bound = customer_positions[j + 1] if j + 1 < n else len(ids)
                affected_stations = tuple(
                    nid for p, nid in enumerate(ids)
                    if left_bound < p < right_bound and nid in instance.station_ids
                )
                units.append(RemovalUnit(
                    route_index=route_index,
                    start_customer_position=customer_positions[i],
                    end_customer_position=customer_positions[j],
                    customer_ids=tuple(ids[p] for p in customer_positions[i:j + 1]),
                    affected_station_ids=affected_stations,
                ))
    return units


def sample_candidate_pool(
    units: Sequence[RemovalUnit],
    *,
    rng: random.Random,
    max_per_route: int = 5,
    max_total: int = 100,
) -> list[RemovalUnit]:
    """Stratified, seeded subsample: singletons first, then bounded longer segments.

    Length-1 units are retained preferentially so the shared customer-removal budget ``k`` is
    attainable whenever the solution has at least ``k`` customers. Remaining slots are filled by
    seeded draws over longer segments (never by ``units[:max_total]``). The final pool is shuffled
    before ranking so arrival order cannot bias any ranking method.
    """
    by_route: dict[int, list[RemovalUnit]] = {}
    for unit in units:
        by_route.setdefault(unit.route_index, []).append(unit)

    stratified: list[RemovalUnit] = []
    for route_index in sorted(by_route):
        bucket = by_route[route_index]
        singletons = [u for u in bucket if len(u.customer_ids) == 1]
        longer = [u for u in bucket if len(u.customer_ids) > 1]
        kept = list(singletons)
        remaining_slots = max(0, max_per_route - len(kept))
        if remaining_slots and longer:
            kept.extend(longer if len(longer) <= remaining_slots else rng.sample(longer, remaining_slots))
        elif not singletons and longer:
            kept = list(longer if len(longer) <= max_per_route else rng.sample(longer, max_per_route))
        stratified.extend(kept)

    # If we still exceed max_total, drop longer segments before dropping singletons.
    if len(stratified) > max_total:
        singles = [u for u in stratified if len(u.customer_ids) == 1]
        others = [u for u in stratified if len(u.customer_ids) > 1]
        if len(singles) >= max_total:
            pool = rng.sample(singles, max_total)
        else:
            need = max_total - len(singles)
            pool = list(singles) + (others if len(others) <= need else rng.sample(others, need))
    else:
        pool = list(stratified)
    rng.shuffle(pool)
    return pool
