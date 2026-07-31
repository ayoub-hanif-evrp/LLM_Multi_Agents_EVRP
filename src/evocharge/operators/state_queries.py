"""State-dependent query helpers for precondition-aware operators (M9A)."""

from __future__ import annotations

from evocharge.operators.generated_api import EntityCandidate, ReadOnlySearchState
from evocharge.operators.primitives import (
    query_charging_detour,
    query_energy_slack,
    query_time_slack,
)
from evocharge.solver.route_utils import customer_sequence_of


def customers_in_route(state: ReadOnlySearchState, route_index: int) -> tuple[str, ...]:
    if route_index < 0 or route_index >= len(state.solution.routes):
        return ()
    return customer_sequence_of(state.solution.routes[route_index], state.instance)


def stations_in_route(state: ReadOnlySearchState, route_index: int) -> tuple[str, ...]:
    if route_index < 0 or route_index >= len(state.solution.routes):
        return ()
    stations = set(state.instance.station_ids)
    return tuple(
        n for n in state.solution.routes[route_index].node_ids if n in stations
    )


def customer_positions_only(
    state: ReadOnlySearchState, route_index: int
) -> tuple[int, ...]:
    """Indices in the route node sequence that are customers (never depot)."""
    if route_index < 0 or route_index >= len(state.solution.routes):
        return ()
    customers = set(state.instance.customer_ids)
    nodes = state.solution.routes[route_index].node_ids
    return tuple(i for i, n in enumerate(nodes) if n in customers)


def non_depot_segments(
    state: ReadOnlySearchState,
    route_index: int,
    min_len: int = 1,
    max_len: int = 4,
) -> tuple[EntityCandidate, ...]:
    """Contiguous customer-only spans (excludes depot and station-only positions)."""
    positions = customer_positions_only(state, route_index)
    if not positions:
        return ()
    nodes = state.solution.routes[route_index].node_ids
    out: list[EntityCandidate] = []
    # Build contiguous runs of customer indices in node space
    runs: list[list[int]] = []
    current: list[int] = [positions[0]]
    for p in positions[1:]:
        if p == current[-1] + 1:
            current.append(p)
        else:
            runs.append(current)
            current = [p]
    runs.append(current)
    for run in runs:
        for length in range(min_len, min(max_len, len(run)) + 1):
            for i in range(0, len(run) - length + 1):
                start = run[i]
                end = run[i + length - 1] + 1
                cust_ids = [
                    nodes[j]
                    for j in range(start, end)
                    if nodes[j] in set(state.instance.customer_ids)
                ]
                if not cust_ids:
                    continue
                eid = f"seg_r{route_index}_{start}_{end}"
                out.append(
                    EntityCandidate(
                        entity_type="segment",
                        entity_id=eid,
                        route_index=route_index,
                        start_index=start,
                        end_index=end,
                        metadata={"customer_ids": cust_ids},
                    )
                )
    return tuple(out)


def rank_customers_by_energy_criticality(
    state: ReadOnlySearchState, route_index: int, k: int = 3
) -> tuple[EntityCandidate, ...]:
    custs = customers_in_route(state, route_index)
    if not custs:
        return ()
    # Lower energy slack at corresponding schedule stops => higher criticality
    route = state.solution.routes[route_index]
    scored: list[tuple[float, str]] = []
    for cid in custs:
        # Find first matching schedule index for time/energy slack proxy
        idx = next(
            (i for i, s in enumerate(route.schedule) if s.node_id == cid),
            0,
        )
        slack = query_energy_slack(state, route_index)
        tw = query_time_slack(state, route_index, idx)
        score = -float(slack) - 0.1 * float(tw)
        scored.append((score, cid))
    scored.sort(reverse=True)
    return tuple(
        EntityCandidate(entity_type="customer", entity_id=cid, route_index=route_index)
        for _, cid in scored[: max(0, k)]
    )


def rank_segments_by_charging_detour_contribution(
    state: ReadOnlySearchState, route_index: int, k: int = 3
) -> tuple[EntityCandidate, ...]:
    segs = non_depot_segments(state, route_index, min_len=1, max_len=3)
    if not segs:
        return ()
    detour = query_charging_detour(state, route_index)
    # Prefer longer segments on high-detour routes
    def _seg_score(s: EntityCandidate) -> tuple[float, int]:
        raw = s.metadata.get("customer_ids")
        n_cust = len(raw) if isinstance(raw, (list, tuple)) else 0
        return (float(detour) * float(n_cust), -(s.start_index or 0))

    ranked = sorted(segs, key=_seg_score, reverse=True)
    return tuple(ranked[: max(0, k)])


def rank_stations_by_detour(
    state: ReadOnlySearchState, route_index: int, k: int = 3
) -> tuple[EntityCandidate, ...]:
    stations = stations_in_route(state, route_index)
    if not stations:
        return ()
    detour = query_charging_detour(state, route_index)
    # Stable: order by appearance, score by shared route detour
    return tuple(
        EntityCandidate(
            entity_type="station",
            entity_id=sid,
            route_index=route_index,
            metadata={"detour": float(detour)},
        )
        for sid in stations[: max(0, k)]
    )


def enumerate_feasible_station_replacements(
    state: ReadOnlySearchState,
    route_index: int,
    station_id: str,
    max_alternatives: int = 5,
) -> tuple[str, ...]:
    """Other stations whose explicit substitution keeps the solution feasible."""
    if station_id not in stations_in_route(state, route_index):
        return ()
    from evocharge.domain.solution import Solution
    from evocharge.solver.feasibility import evaluate_feasibility
    from evocharge.solver.propagation import propagate_route

    route = state.solution.routes[route_index]
    out: list[str] = []
    for alt in state.instance.station_ids:
        if alt == station_id:
            continue
        nodes = tuple(alt if n == station_id else n for n in route.node_ids)
        trial_route = propagate_route(state.instance, nodes, vehicle_index=route_index)
        routes = list(state.solution.routes)
        routes[route_index] = trial_route
        report = evaluate_feasibility(state.instance, Solution(routes=tuple(routes)))
        if report.feasible:
            out.append(alt)
        if len(out) >= max_alternatives:
            break
    return tuple(out)


def query_downstream_charging_delay(
    state: ReadOnlySearchState, route_index: int
) -> float:
    return float(query_charging_detour(state, route_index))


def query_insertion_feasibility(
    state: ReadOnlySearchState, route_index: int, customer_id: str
) -> float:
    """Soft score in [0,1]: 1 if customer already on a route, else energy-slack proxy."""
    _ = customer_id
    if route_index < 0 or route_index >= len(state.solution.routes):
        return 0.0
    slack = query_energy_slack(state, route_index)
    return max(0.0, min(1.0, 0.5 + 0.01 * float(slack)))
