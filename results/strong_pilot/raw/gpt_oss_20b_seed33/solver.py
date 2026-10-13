import random
from typing import List, Dict, Any

# Physics utilities
from evrptw_autolab.problem.physics import (
    distance,
    travel_time,
    energy_required,
    full_recharge,
    propagate_route,
)


def is_route_feasible(instance, route: List[str]) -> bool:
    """
    Check whether a route is feasible with respect to battery, time windows,
    and depot placement.

    Parameters
    ----------
    instance : EVRPTWInstance
        Problem instance.
    route : list[str]
        Sequence of node IDs starting and ending at the depot.

    Returns
    -------
    bool
        True if the route is feasible, False otherwise.
    """
    # Propagate the route to obtain StopState objects
    states = propagate_route(instance, route)

    # Basic checks: start and end at depot, no internal depot visits
    depot_id = instance.depot_id
    if states[0].node_id != depot_id or states[-1].node_id != depot_id:
        return False
    for mid_state in states[1:-1]:
        if mid_state.node_id == depot_id:
            return False

    # Check battery and time windows for each stop
    for state in states:
        node = instance.node_map[state.node_id]
        # Battery must never be negative
        if state.battery_arrival < 0:
            return False
        # Time window constraints apply only to customers
        if node.kind == "customer":
            if state.arrival_time < node.ready_time or state.arrival_time > node.due_time:
                return False
    return True

def sum_route_distance(instance, routes: List[List[str]]) -> float:
    """
    Compute the total Euclidean distance of all routes.

    Parameters
    ----------
    instance : EVRPTWInstance
        Problem instance.
    routes : list[list[str]]
        List of routes.

    Returns
    -------
    float
        Sum of distances between consecutive nodes in all routes.
    """
    total = 0.0
    for route in routes:
        for i in range(len(route) - 1):
            a = instance.node_map[route[i]]
            b = instance.node_map[route[i + 1]]
            total += distance(a, b)
    return total

def find_feasible_route(instance, customer_id: str) -> List[str] | None:
    """
    Attempt to build a feasible route for a single customer using a
    small set of patterns that include optional charging stations.

    Parameters
    ----------
    instance : EVRPTWInstance
        Problem instance.
    customer_id : str
        ID of the customer to serve.

    Returns
    -------
    list[str] | None
        A feasible route or None if none could be found.
    """
    depot_id = instance.depot_id
    station_ids = instance.station_ids

    # Pattern 1: depot -> customer -> depot
    route = [depot_id, customer_id, depot_id]
    if is_route_feasible(instance, route):
        return route

    # Pattern 2: depot -> station -> customer -> station -> depot
    for station_id in station_ids:
        route = [depot_id, station_id, customer_id, station_id, depot_id]
        if is_route_feasible(instance, route):
            return route

    # Pattern 3: depot -> customer -> station -> depot
    for station_id in station_ids:
        route = [depot_id, customer_id, station_id, depot_id]
        if is_route_feasible(instance, route):
            return route

    # Pattern 4: depot -> s1 -> s2 -> customer -> s2 -> s1 -> depot
    for i in range(len(station_ids)):
        for j in range(len(station_ids)):
            if i == j:
                continue
            s1 = station_ids[i]
            s2 = station_ids[j]
            route = [depot_id, s1, s2, customer_id, s2, s1, depot_id]
            if is_route_feasible(instance, route):
                return route

    # No feasible route found
    return None

def solve(instance, seed: int, time_limit_s: float) -> Dict[str, Any]:
    """Construct a feasible solution for the EVRPTW instance using a
    greedy multi‑customer routing heuristic.
    """
    routes = build_routes(instance, seed)

    metadata = {
        "num_vehicles": len(routes),
        "total_distance": sum_route_distance(instance, routes),
    }

    return {"routes": routes, "metadata": metadata}

def build_routes(instance, seed: int) -> List[List[str]]:
    """Construct routes by greedily grouping customers while respecting
    capacity, time windows, and battery constraints.  The routine
    attempts to add customers to the current route; if the route
    becomes infeasible it starts a new route.  When a single
    customer cannot be served in a simple route, the helper
    `find_feasible_route` is used to create a dedicated route.
    """
    random.seed(seed)
    depot_id = instance.depot_id
    station_ids = list(instance.station_ids)
    customers = list(instance.customer_ids)

    # Randomize order to avoid deterministic bad patterns
    random.shuffle(customers)

    routes: List[List[str]] = []
    current_customers: List[str] = []
    current_load = 0.0

    for cust_id in customers:
        node = instance.node_map[cust_id]
        # Check capacity
        if current_load + node.demand > instance.vehicle.capacity:
            # finalize current route
            if current_customers:
                routes.append([depot_id] + current_customers + [depot_id])
            # start new route
            current_customers = [cust_id]
            current_load = node.demand
            continue

        # Tentatively add to current route
        tentative = [depot_id] + current_customers + [cust_id] + [depot_id]
        if is_route_feasible(instance, tentative):
            current_customers.append(cust_id)
            current_load += node.demand
            continue

        # Try inserting a station before the new customer
        feasible_with_station = None
        for station_id in station_ids:
            route_with_station = (
                [depot_id]
                + current_customers
                + [station_id]
                + [cust_id]
                + [depot_id]
            )
            if is_route_feasible(instance, route_with_station):
                feasible_with_station = route_with_station
                break

        if feasible_with_station:
            # finalize current route
            if current_customers:
                routes.append([depot_id] + current_customers + [depot_id])
            # start new route with station and customer
            routes.append(feasible_with_station)
            current_customers = []
            current_load = 0.0
            continue

        # If still infeasible, start a new route with the customer alone
        single_route = find_feasible_route(instance, cust_id)
        if single_route is None:
            raise RuntimeError(f"Could not find a feasible route for customer {cust_id}")
        # finalize current route
        if current_customers:
            routes.append([depot_id] + current_customers + [depot_id])
        routes.append(single_route)
        current_customers = []
        current_load = 0.0

    # Append any remaining customers
    if current_customers:
        routes.append([depot_id] + current_customers + [depot_id])

    return routes

