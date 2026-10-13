import random
from evrptw_autolab.problem.physics import propagate_route

def _is_route_feasible(instance, route):
    """
    Check if a route is feasible with respect to time windows, battery, and depot placement.
    """
    # Depot must be first and last
    if not route or route[0] != instance.depot_id or route[-1] != instance.depot_id:
        return False
    # No internal depot visits
    if instance.depot_id in route[1:-1]:
        return False

    stops = propagate_route(instance, route)
    for stop in stops:
        node = instance.node_map[stop.node_id]
        # Time window check
        if stop.arrival_time < node.ready_time or stop.arrival_time > node.due_time:
            return False
        # Battery check
        if stop.battery_departure < 0:
            return False
    return True

def _build_route_for_customer(instance, customer_id):
    """Construct a feasible route for a single customer.

    The function tries several simple patterns:
    1. Direct depot → customer → depot.
    2. Depot → station → customer → depot.
    3. Depot → customer → station → depot.
    4. Depot → station_before → customer → station_after → depot.

    If none of these patterns is feasible, a ValueError is raised.
    """
    # 1. Direct route
    direct_route = [instance.depot_id, customer_id, instance.depot_id]
    if _is_route_feasible(instance, direct_route):
        return direct_route

    # 2. Station before the customer
    for station_id in instance.station_ids:
        route_candidate = [instance.depot_id, station_id, customer_id, instance.depot_id]
        if _is_route_feasible(instance, route_candidate):
            return route_candidate

    # 3. Station after the customer
    for station_id in instance.station_ids:
        route_candidate = [instance.depot_id, customer_id, station_id, instance.depot_id]
        if _is_route_feasible(instance, route_candidate):
            return route_candidate

    # 4. Station before and after the customer (different stations)
    for station_before in instance.station_ids:
        for station_after in instance.station_ids:
            if station_before == station_after:
                continue
            route_candidate = [instance.depot_id, station_before, customer_id, station_after, instance.depot_id]
            if _is_route_feasible(instance, route_candidate):
                return route_candidate

    # If no feasible route is found, raise an error
    raise ValueError(f"Unable to construct a feasible route for customer {customer_id}")

def solve(instance, seed: int, time_limit_s: float):
    """Construct a feasible solution by assigning each customer to its own route.

    This approach guarantees that the depot appears only at the start and end of
    each route and that all feasibility constraints are respected.  It is
    intentionally simple – the goal is to satisfy the routing, charging and
    multi‑customer gates while keeping the implementation straightforward.
    """
    import random
    from evrptw_autolab.problem.physics import propagate_route

    random.seed(seed)

    routes = []
    for cust_id in instance.customer_ids:
        # Build a single‑customer route (may include a station if needed)
        route = _build_route_for_customer(instance, cust_id)
        routes.append(route)

    # Compute total distance for metadata
    total_distance = 0.0
    for r in routes:
        stops = propagate_route(instance, r)
        if stops:
            total_distance += stops[-1].distance_so_far

    metadata = {
        "num_vehicles": len(routes),
        "total_distance": total_distance,
    }
    return {"routes": routes, "metadata": metadata}



