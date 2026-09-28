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
            for cid in unassigned_customers:
                candidate_route = [depot, cid, depot]
                if is_battery_feasible(instance, candidate_route):
                    routes.append(candidate_route)
                    unassigned_customers.remove(cid)
                else:
                    new_route = insert_charging_station(instance, candidate_route)
                    if new_route:
                        routes.append(new_route)
                        unassigned_customers.remove(cid)
                    else:
                        raise ValueError("Route is not feasible after inserting charging station.")
    
    # Attempt to merge routes to minimize the number of vehicles
    merged_routes = merge_routes(instance, routes)
    
    return {"routes": merged_routes, "metadata": {"seed": seed}}

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

def merge_routes(instance, routes):
    # Sort routes by the number of customers served
    routes.sort(key=lambda r: len(r), reverse=True)
    
    merged_routes = []
    for route in routes:
        if not merged_routes:
            merged_routes.append(route)
            continue
        
        for i, merged_route in enumerate(merged_routes):
            candidate_route = merged_route + route[1:-1] + [route[-1]]
            if is_battery_feasible(instance, candidate_route):
                merged_routes[i] = candidate_route
                break
        else:
            merged_routes.append(route)
    
    return merged_routes


