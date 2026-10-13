import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    """Main solver function for EVRPTW problem."""
    random.seed(seed)
    routes = build_initial_routes(instance)
    routes = insert_charging_stops(instance, routes)
    if not validate_routes(instance, routes):
        routes = build_initial_routes(instance)  # Fallback if validation fails
    return CandidateSolution(routes=routes)

def build_initial_routes(instance):
    """Build initial routes by assigning customers to vehicles."""
    unassigned = list(instance.customer_ids)
    routes = []
    while unassigned:
        route = [instance.depot_id]
        current_load = 0
        current_time = instance.node_map[instance.depot_id].ready_time
        current_battery = instance.vehicle.start_soc * instance.vehicle.battery_capacity

        while unassigned:
            # Find the nearest unassigned customer that fits
            best_customer = None
            best_distance = float('inf')
            best_index = -1

            for idx, cust_id in enumerate(unassigned):
                cust = instance.node_map[cust_id]
                dist = distance(instance.node_map[route[-1]], cust)
                time_needed = travel_time(instance.node_map[route[-1]], cust, instance.vehicle)
                new_time = current_time + time_needed + cust.service_time
                energy_needed = energy_required(instance.node_map[route[-1]], cust, instance.vehicle)

                if (current_load + cust.demand <= instance.vehicle.capacity and
                    new_time <= cust.due_time and
                    current_battery - energy_needed >= 0):
                    if dist < best_distance:
                        best_distance = dist
                        best_customer = cust_id
                        best_index = idx

            if best_customer is None:
                break

            # Add to route
            route.append(best_customer)
            current_load += instance.node_map[best_customer].demand
            current_time += travel_time(instance.node_map[route[-2]], instance.node_map[best_customer], instance.vehicle)
            current_battery -= energy_required(instance.node_map[route[-2]], instance.node_map[best_customer], instance.vehicle)
            unassigned.pop(best_index)

        route.append(instance.depot_id)
        routes.append(route)

    return routes

def insert_charging_stops(instance, routes):
    """Insert charging stops where needed in the routes."""
    new_routes = []
    for route in routes:
        # Propagate the route to get stop states
        stops = propagate_route(instance, route)
        
        # Check if charging is needed
        needs_charging = False
        for stop in stops:
            if stop.battery_departure < instance.vehicle.battery_capacity * 0.3 and instance.node_map[stop.node_id].kind != "station":
                needs_charging = True
                break
        
        if not needs_charging:
            new_routes.append(route)
            continue
        
        # Find the best place to insert a charging station
        best_insert_pos = -1
        best_station = None
        min_battery = float('inf')
        
        for i, stop in enumerate(stops[:-1]):  # Exclude the last stop (depot)
            if stop.battery_departure < min_battery and instance.node_map[stop.node_id].kind != "station":
                min_battery = stop.battery_departure
                best_insert_pos = i
                
                # Find the nearest station to insert
                nearest_station = None
                min_dist = float('inf')
                for station_id in instance.station_ids:
                    station = instance.node_map[station_id]
                    dist = distance(instance.node_map[stop.node_id], station)
                    if dist < min_dist:
                        min_dist = dist
                        nearest_station = station_id
                
                if nearest_station:
                    best_station = nearest_station
        
        if best_insert_pos != -1 and best_station:
            # Insert the station into the route
            new_route = route[:best_insert_pos+1] + [best_station] + route[best_insert_pos+1:]
            
            # Re-propagate the route with the new station
            new_stops = propagate_route(instance, new_route)
            
            # Verify the charging was effective
            for i, stop in enumerate(new_stops):
                if stop.node_id == best_station:
                    if stop.battery_departure < instance.vehicle.battery_capacity * 0.9:
                        # Charging was not effective, try another station
                        new_routes.append(route)
                    else:
                        new_routes.append(new_route)
                    break
            else:
                new_routes.append(route)
        else:
            new_routes.append(route)
    
    return new_routes

def validate_routes(instance, routes):
    """Validate routes for feasibility."""
    # Check that all customers are visited exactly once
    visited = set()
    for route in routes:
        for node_id in route:
            if node_id in instance.customer_ids:
                if node_id in visited:
                    return False
                visited.add(node_id)
    if len(visited) != instance.n_customers:
        return False

    # Check that routes start and end at depot
    for route in routes:
        if route[0] != instance.depot_id or route[-1] != instance.depot_id:
            return False

    # Check that no internal depot visits
    for route in routes:
        for node_id in route[1:-1]:
            if node_id == instance.depot_id:
                return False

    # Check that all node IDs are strings
    for route in routes:
        for node_id in route:
            if not isinstance(node_id, str):
                return False

    return True



