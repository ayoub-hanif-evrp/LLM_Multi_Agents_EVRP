import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    """Main solver function for EVRPTW problem."""
    random.seed(seed)
    routes = build_initial_routes(instance)
    routes = insert_charging_stops(instance, routes)
    return {"routes": routes, "metadata": {}}

def build_initial_routes(instance):
    """Build initial routes visiting all customers exactly once, respecting capacity and time windows."""
    unvisited = list(instance.customer_ids)
    routes = []
    current_route = [instance.depot_id]

    while unvisited:
        nearest = find_nearest(unvisited, current_route[-1], instance)
        if nearest is None:
            break

        test_route = current_route + [nearest]
        stops = propagate_route(instance, test_route)

        valid = True
        for stop in stops:
            node = instance.node_map[stop.node_id]
            if (stop.load > instance.vehicle.capacity or
                stop.arrival_time < node.ready_time or
                stop.departure_time > node.due_time):
                valid = False
                break

        if valid:
            current_route.append(nearest)
            unvisited.remove(nearest)
        else:
            if len(current_route) > 1:
                routes.append(current_route)
            current_route = [instance.depot_id]

    if len(current_route) > 1:
        routes.append(current_route)

    # Ensure all routes start and end at depot
    final_routes = []
    for route in routes:
        if route[0] != instance.depot_id:
            route.insert(0, instance.depot_id)
        if route[-1] != instance.depot_id:
            route.append(instance.depot_id)
        final_routes.append(route)

    return final_routes if final_routes else [[instance.depot_id]]

def find_nearest(unvisited, current_node_id, instance):
    """Find the nearest unvisited customer to the current node."""
    min_dist = float('inf')
    nearest = None
    current = instance.node_map[current_node_id]

    for customer_id in unvisited:
        customer = instance.node_map[customer_id]
        dist = distance(current, customer)
        if dist < min_dist:
            min_dist = dist
            nearest = customer_id

    return nearest

def insert_charging_stops(instance, routes):
    """Insert charging stops when needed in the routes, ensuring feasibility."""
    new_routes = []
    for route in routes:
        new_route = list(route)
        i = 0
        while i < len(new_route) - 1:
            # Check battery level before next move
            current_battery = get_current_battery(new_route[:i+1], instance)
            current_node = instance.node_map[new_route[i]]
            next_node = instance.node_map[new_route[i+1]]

            energy_needed = energy_required(current_node, next_node, instance.vehicle)
            if current_battery < energy_needed:
                # Find nearest charging station
                station = find_nearest_station(current_node, instance)
                if station:
                    # Insert station before next node
                    new_route.insert(i+1, station.id)
                    # Update battery after charging
                    stops = propagate_route(instance, new_route[:i+2])
                    if stops and stops[-1].node_id == station.id:
                        current_battery = stops[-1].battery_departure
                    i += 1  # Skip the station in next iteration
            i += 1
        new_routes.append(new_route)
    return new_routes

def get_current_battery(route, instance):
    """Calculate current battery level at the end of the route."""
    if not route:
        return instance.vehicle.battery_capacity * instance.vehicle.start_soc

    stops = propagate_route(instance, route)
    return stops[-1].battery_departure if stops else instance.vehicle.battery_capacity * instance.vehicle.start_soc

def find_nearest_station(current_node, instance):
    """Find the nearest charging station to the current node."""
    min_dist = float('inf')
    nearest = None

    for station in instance.stations:
        dist = distance(current_node, station)
        if dist < min_dist:
            min_dist = dist
            nearest = station

    return nearest

