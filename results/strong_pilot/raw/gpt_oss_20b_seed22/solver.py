import random
from evrptw_autolab.problem.physics import (
    distance,
    travel_time,
    energy_required,
    full_recharge,
    propagate_route,
)


def _is_route_feasible(instance, vehicle, route_ids):
    """
    Check feasibility of a route by propagating it and inspecting the resulting StopState list.
    """
    stops = propagate_route(instance, route_ids)

    # Route must start and end at the depot
    if stops[0].node_id != instance.depot_id or stops[-1].node_id != instance.depot_id:
        return False

    for stop in stops:
        node = instance.node_map[stop.node_id]

        # Capacity constraint (only customers have load)
        if node.kind == "customer":
            if stop.load > vehicle.capacity:
                return False
            # Time‑window constraints
            if stop.arrival_time > node.due_time:
                return False
            # Arrival before ready_time is allowed – the evaluator will wait automatically

        # Battery must never be negative
        if stop.battery_departure < 0:
            return False

    return True

def _find_feasible_route_for_customer(instance, vehicle, customer_id):
    """Try to build a feasible route for a single customer.
    The route format is: depot -> (optional station) -> customer -> (optional station) -> depot."""
    depot_id = instance.depot_id
    # 1. Direct route without charging
    route = [depot_id, customer_id, depot_id]
    if _is_route_feasible(instance, vehicle, route):
        return route
    # 2. Insert a charging station before the customer
    for station_id in instance.station_ids:
        route = [depot_id, station_id, customer_id, depot_id]
        if _is_route_feasible(instance, vehicle, route):
            return route
    # 3. Insert a charging station after the customer
    for station_id in instance.station_ids:
        route = [depot_id, customer_id, station_id, depot_id]
        if _is_route_feasible(instance, vehicle, route):
            return route
    # 4. Try two stations (before and after)
    for before in instance.station_ids:
        for after in instance.station_ids:
            route = [depot_id, before, customer_id, after, depot_id]
            if _is_route_feasible(instance, vehicle, route):
                return route
    # 5. Try two stations before the customer
    for b1 in instance.station_ids:
        for b2 in instance.station_ids:
            route = [depot_id, b1, b2, customer_id, depot_id]
            if _is_route_feasible(instance, vehicle, route):
                return route
    # 6. Try two stations after the customer
    for a1 in instance.station_ids:
        for a2 in instance.station_ids:
            route = [depot_id, customer_id, a1, a2, depot_id]
            if _is_route_feasible(instance, vehicle, route):
                return route
    # 7. Try three stations before the customer
    for b1 in instance.station_ids:
        for b2 in instance.station_ids:
            for b3 in instance.station_ids:
                route = [depot_id, b1, b2, b3, customer_id, depot_id]
                if _is_route_feasible(instance, vehicle, route):
                    return route
    # 8. Try three stations after the customer
    for a1 in instance.station_ids:
        for a2 in instance.station_ids:
            for a3 in instance.station_ids:
                route = [depot_id, customer_id, a1, a2, a3, depot_id]
                if _is_route_feasible(instance, vehicle, route):
                    return route
    # No feasible route found
    return None

def solve(instance, seed: int, time_limit_s: float):
    """
    Construct a simple feasible solution:
    one vehicle per customer, inserting a charging station if necessary.
    """
    random.seed(seed)

    vehicle = instance.vehicle
    routes = []

    for customer_id in instance.customer_ids:
        route = _find_feasible_route_for_customer(instance, vehicle, customer_id)
        if route is None:
            raise RuntimeError(f"Could not find a feasible route for customer {customer_id}")
        routes.append(route)

    return {"routes": routes, "metadata": {"solver": "simple_nearest_with_charging"}}

