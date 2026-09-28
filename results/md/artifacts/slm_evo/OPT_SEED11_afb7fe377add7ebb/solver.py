from evrptw_autolab.problem.physics import distance, energy_required, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    depot = instance.depot_id
    routes = []
    unassigned_customers = list(instance.customer_ids)
    
    while unassigned_customers:
        route = [depot]
        for cid in unassigned_customers:
            candidate_route = route + [cid, depot]
            if is_battery_feasible(instance, candidate_route):
                route = candidate_route
                unassigned_customers.remove(cid)
            else:
                break
        
        if len(route) > 2:
            routes.append(route)
        else:
            # If no feasible route is found, try inserting a charging station
            for cid in unassigned_customers:
                candidate_route = route + [cid, depot]
                new_route = insert_charging_station(instance, candidate_route)
                if new_route:
                    routes.append(new_route)
                    unassigned_customers.remove(cid)
                    break
            else:
                # If still no feasible route, assign the customer to a new route
                routes.append([depot, cid, depot])
                unassigned_customers.remove(cid)
    
    # Attempt to merge routes to minimize the number of vehicles
    routes = merge_routes(instance, routes)
    
    # Further optimize routes by reordering customers
    routes = optimize_routes(instance, routes)
    
    return {"routes": routes, "metadata": {"seed": seed}}


def merge_routes(instance, routes):
    # Sort routes by the number of customers served
    routes.sort(key=lambda r: len(r), reverse=True)
    
    merged_routes = []
    for route in routes:
        if not merged_routes:
            merged_routes.append(route)
            continue
        
        for i, merged_route in enumerate(merged_routes):
            candidate_route = merged_route + route[1:-1] + [merged_route[-1]]
            if is_battery_feasible(instance, candidate_route):
                merged_routes[i] = candidate_route
                break
        else:
            merged_routes.append(route)
    
    return merged_routes

def is_battery_feasible(instance, route):
    states = propagate_route(instance, route)
    return all(state.battery_arrival >= 0 for state in states)

def insert_charging_station(instance, route):
    for station_id in instance.station_ids:
        for i in range(1, len(route)):
            new_route = route[:i] + [station_id] + route[i:]
            if is_battery_feasible(instance, new_route):
                return new_route
    return None


def optimize_routes(instance, routes):
    # Reorder customers in each route to minimize total distance
    for i, route in enumerate(routes):
        if len(route) <= 2:
            continue
        
        # Remove depot from the route for optimization
        route_no_depot = route[1:-1]
        optimized_route = optimize_route(instance, route_no_depot)
        
        # Reinsert depot at the start and end
        routes[i] = [route[0]] + optimized_route + [route[-1]]
    
    return routes


def optimize_route(instance, route):
    # Implement a simple 2-opt heuristic to reorder customers
    n = len(route)
    if n <= 1:
        return route
    
    best_route = route.copy()
    improved = True
    
    while improved:
        improved = False
        for i in range(n - 1):
            for j in range(i + 1, n):
                candidate_route = route[:i] + route[i:j+1][::-1] + route[j+1:]
                if is_battery_feasible(instance, [route[0]] + candidate_route + [route[-1]]) and total_distance(instance, candidate_route) < total_distance(instance, best_route):
                    best_route = candidate_route
                    improved = True
    
    return best_route


def total_distance(instance, route):
    total_d = 0
    for i in range(len(route) - 1):
        total_d += distance(instance.node_map[route[i]], instance.node_map[route[i+1]])
    return total_d

def merge_routes(instance, routes):
    # Sort routes by the number of customers served
    routes.sort(key=lambda r: len(r), reverse=True)
    
    merged_routes = []
    for route in routes:
        if not merged_routes:
            merged_routes.append(route)
            continue
        
        for i, merged_route in enumerate(merged_routes):
            candidate_route = merged_route + route[1:-1] + [merged_route[-1]]
            if is_battery_feasible(instance, candidate_route):
                merged_routes[i] = candidate_route
                break
        else:
            merged_routes.append(route)
    
    return merged_routes

def is_battery_feasible(instance, route):
    states = propagate_route(instance, route)
    return all(state.battery_arrival >= 0 for state in states)

def insert_charging_station(instance, route):
    for station_id in instance.station_ids:
        for i in range(1, len(route)):
            new_route = route[:i] + [station_id] + route[i:]
            if is_battery_feasible(instance, new_route):
                return new_route
    return None



