"""Search-state features. Instance names and future objectives are not features."""

from __future__ import annotations

from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2


def search_context(spec: ProblemSpecV2, solution: SolutionV2) -> dict[str, float]:
    """Numeric state of the current solution. Filenames and instance ids are omitted."""
    customers = [node for node in spec.nodes if node.kind in {"customer", "pickup", "delivery"}]
    stations = [node for node in spec.nodes if node.kind == "station"]
    ratios: list[float] = []
    assignments = list(solution.vehicle_assignments)
    vehicles = {vehicle.type_id: vehicle for vehicle in spec.vehicle_types}
    for index, route in enumerate(solution.routes):
        type_id = assignments[index] if index < len(assignments) else ""
        vehicle = vehicles.get(type_id)
        capacity = float(vehicle.capacity) if vehicle is not None and vehicle.capacity else 0.0
        if capacity <= 0.0:
            continue
        demand = 0.0
        for stop in route:
            if stop.event == "depot":
                continue
            demand += float(spec.node_map[stop.node_id].demand)
        ratios.append(demand / capacity)
    utilization = sum(ratios) / len(ratios) if ratios else 0.0
    return {
        "customer_count": float(len(customers)),
        "route_count": float(len(solution.routes)),
        "route_utilization": float(utilization),
        "station_count": float(len(stations)),
    }
