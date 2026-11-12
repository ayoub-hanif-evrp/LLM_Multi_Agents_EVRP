"""Search-state features. Instance names and future objectives are not features."""

from __future__ import annotations

from evrptw_autolab.backbone.util import vehicle_for_route
from evrptw_autolab.discovery.policy_language import needs_expensive_context
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.v2.route_simulator import simulate_route
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2


def context_for_operator(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    operator: OperatorSpec | None = None,
) -> dict[str, float]:
    """Build search context, enabling expensive slack features when the operator needs them."""
    from evrptw_autolab.discovery.policy_language import EXPENSIVE_CONTEXT_FEATURES

    expensive = False
    if operator is not None:
        expensive = needs_expensive_context(
            operator.applicability_rule,
            operator.candidate_scoring_policy,
            *operator.hard_preconditions,
        ) or bool(set(operator.required_features) & EXPENSIVE_CONTEXT_FEATURES)
    return search_context(spec, solution, expensive=expensive)


def search_context(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    expensive: bool = False,
) -> dict[str, float]:
    """Numeric state of the current solution. Filenames and instance ids are omitted.

    Peak load is always computed. Battery and window slack use route simulation only
    when ``expensive`` is true, so applicability checks stay cheap by default.
    """
    customers = [node for node in spec.nodes if node.kind in {"customer", "pickup", "delivery"}]
    stations = [node for node in spec.nodes if node.kind == "station"]
    peak_ratios: list[float] = []
    battery_slacks: list[float] = []
    window_slacks: list[float] = []
    for index, route in enumerate(solution.routes):
        try:
            vehicle = vehicle_for_route(spec, solution, index)
        except ValueError:
            continue
        capacity = float(vehicle.capacity) if vehicle.capacity else 0.0
        peak = _peak_load(spec, route)
        if capacity > 0.0:
            peak_ratios.append(peak / capacity)
        if expensive and spec.capabilities.battery and vehicle.is_electric and not vehicle.is_conventional:
            battery_slacks.append(_battery_slack(spec, route, vehicle))
        if expensive and spec.capabilities.time_windows:
            window_slacks.append(_window_slack(spec, route, vehicle))
    utilization = sum(peak_ratios) / len(peak_ratios) if peak_ratios else 0.0
    return {
        "customer_count": float(len(customers)),
        "route_count": float(len(solution.routes)),
        "route_utilization": float(utilization),
        "peak_load_ratio": float(utilization),
        "station_count": float(len(stations)),
        "battery_slack": float(min(battery_slacks) if battery_slacks else 0.0),
        "time_window_slack": float(min(window_slacks) if window_slacks else 0.0),
    }


def _peak_load(spec: ProblemSpecV2, route: list) -> float:
    """Highest onboard load along the route. Signed PD demands do not cancel this."""
    load = 0.0
    peak = 0.0
    for stop in route:
        if stop.event == "depot":
            continue
        load += float(spec.node_map[stop.node_id].demand)
        peak = max(peak, load)
    return peak


def _battery_slack(spec: ProblemSpecV2, route: list, vehicle) -> float:
    try:
        trajectory, errors = simulate_route(spec, route, vehicle)
    except (KeyError, ValueError):
        return -1.0
    if errors or not trajectory:
        return -1.0
    capacity = float(vehicle.battery_capacity or 0.0)
    if capacity <= 0.0:
        return 0.0
    lowest = min(float(state.battery_arrival) for state in trajectory)
    return lowest / capacity


def _window_slack(spec: ProblemSpecV2, route: list, vehicle) -> float:
    try:
        trajectory, errors = simulate_route(spec, route, vehicle)
    except (KeyError, ValueError):
        return -1.0
    if errors or not trajectory:
        return -1.0
    slacks: list[float] = []
    for state in trajectory:
        node = spec.node_map[state.node_id]
        due = float(node.due_time)
        if due != due or due in (float("inf"), float("-inf")):
            continue
        slacks.append(due - float(state.arrival_time))
    return min(slacks) if slacks else 0.0
