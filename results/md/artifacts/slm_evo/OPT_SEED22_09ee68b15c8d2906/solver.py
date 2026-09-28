from evrptw_autolab.problem.physics import distance, energy_required, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    depot = instance.depot_id
    routes = []
    
    # Sort customers by demand to try to pack them into fewer vehicles
    sorted_customers = sorted(instance.customer_ids, key=lambda cid: instance.node_map[cid].demand, reverse=True)
    
    for cid in sorted_customers:
        route = [depot, cid, depot]
        states = propagate_route(instance, route)
        
        # Check if the route is battery-feasible
        if all(state.battery_arrival >= 0 for state in states):
            routes.append(route)
            continue
        
        # If not battery-feasible, insert a charging station
        for station_id in instance.station_ids:
            for i in range(1, len(route)):
                new_route = route[:i] + [station_id] + route[i:]
                new_states = propagate_route(instance, new_route)
                
                if all(state.battery_arrival >= 0 for state in new_states):
                    routes.append(new_route)
                    break
            else:
                continue
            break
    
    # Try to merge routes to minimize the number of vehicles
    merged_routes = []
    for route in routes:
        merged = False
        for i, merged_route in enumerate(merged_routes):
            new_route = merged_route + route[1:]  # Try appending the current route to an existing one
            new_states = propagate_route(instance, new_route)
            
            if all(state.battery_arrival >= 0 for state in new_states):
                merged_routes[i] = new_route
                merged = True
                break
        if not merged:
            merged_routes.append(route)
    
    # Sort merged routes by total distance
    merged_routes.sort(key=lambda route: calculate_total_distance(instance, [route]))
    
    # Further optimize by trying to merge routes with charging stations
    optimized_routes = merge_routes_with_charging_stations(instance, merged_routes)
    
    return {"routes": optimized_routes, "metadata": {"seed": seed}}

def merge_routes_with_charging_stations(instance, routes):
    optimized_routes = []
    for route in routes:
        merged = False
        for i, optimized_route in enumerate(optimized_routes):
            combined_route = optimized_route + route[1:]
            combined_route, combined_states = evaluate_route_with_charging(instance, combined_route)
            if combined_route is not None:
                optimized_routes[i] = combined_route
                merged = True
                break
        if not merged:
            optimized_routes.append(route)
    return optimized_routes

def can_merge_routes(instance, route1, route2):
    combined_route = route1 + route2[1:]
    states = propagate_route(instance, combined_route)
    return all(state.battery_arrival >= 0 for state in states)

def merge_routes(instance, route1, route2):
    return route1 + route2[1:]

def calculate_total_distance(instance, routes):
    total_distance = 0
    for route in routes:
        for i in range(len(route) - 1):
            total_distance += distance(instance.node_map[route[i]], instance.node_map[route[i + 1]])
    return total_distance

def evaluate_route_with_charging(instance, route):
    best_route = None
    best_states = None
    best_distance = float('inf')
    
    # Try inserting charging stations at each possible position
    for station_id in instance.station_ids:
        for i in range(1, len(route)):
            new_route = route[:i] + [station_id] + route[i:]
            new_states = propagate_route(instance, new_route)
            
            # Check for WINDOW fault
            if all(state.battery_arrival >= 0 for state in new_states) and not any(state.service_start > instance.node_map[state.node_id].due_time for state in new_states):
                new_distance = calculate_total_distance(instance, [new_route])
                if new_distance < best_distance:
                    best_distance = new_distance
                    best_route = new_route
                    best_states = new_states
    
    return best_route, best_states




