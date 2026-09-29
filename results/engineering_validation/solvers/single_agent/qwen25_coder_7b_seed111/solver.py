from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    vehicle = instance.vehicle
    
    # Initialize routes with the depot
    routes = [[depot_id] for _ in range(len(customers) + 1)]
    
    # Assign customers to routes
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        min_distance = float('inf')
        best_route_index = -1
        
        for i, route in enumerate(routes):
            if len(route) > 1 and route[-1] == depot_id:
                continue
            last_node = instance.node_map[route[-1]]
            dist = distance(last_node, customer)
            if dist < min_distance:
                min_distance = dist
                best_route_index = i
        
        if best_route_index == -1:
            # If no valid route found, create a new one
            routes.append([depot_id, customer_id, depot_id])
        else:
            routes[best_route_index].append(customer_id)
    
    # Ensure the depot is at the end of each route
    for route in routes:
        if route[-1] != depot_id:
            route.append(depot_id)
    
    # Return the solution
    return {"routes": routes, "metadata": {}}