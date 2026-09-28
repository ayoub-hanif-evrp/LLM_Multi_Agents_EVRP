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
    
    # Further optimize by trying to merge routes again
    optimized_routes = merge_routes(merged_routes, instance)
    
    return {"routes": optimized_routes, "metadata": {"seed": seed}}

def calculate_total_distance(instance, routes):
    total_distance = 0
    for route in routes:
        for i in range(len(route) - 1):
            total_distance += distance(instance.node_map[route[i]], instance.node_map[route[i + 1]])
    return total_distance


def merge_routes(routes, instance):
    while True:
        merged = False
        for i in range(len(routes) - 1):
            for j in range(i + 1, len(routes)):
                new_route = routes[i] + routes[j][1:]  # Try appending one route to another
                new_states = propagate_route(instance, new_route)
                
                if all(state.battery_arrival >= 0 for state in new_states):
                    routes[i] = new_route
                    del routes[j]
                    merged = True
                    break
            if merged:
                break
        if not merged:
            break
    
    return routes

def calculate_total_distance(instance, routes):
    total_distance = 0
    for route in routes:
        for i in range(len(route) - 1):
            total_distance += distance(instance.node_map[route[i]], instance.node_map[route[i + 1]])
    return total_distance


