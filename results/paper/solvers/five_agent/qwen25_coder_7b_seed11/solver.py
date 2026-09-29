from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id]]
    
    # Assign customers to routes
    for customer_id in instance.customer_ids:
        min_cost = float('inf')
        best_route_index = -1
        
        for i, route in enumerate(routes):
            if len(route) == 1:
                cost = distance(instance.node_map[route[0]], instance.node_map[customer_id])
            else:
                cost = distance(instance.node_map[route[-1]], instance.node_map[customer_id])
            
            if cost < min_cost:
                min_cost = cost
                best_route_index = i
        
        routes[best_route_index].append(customer_id)
        routes[best_route_index].append(instance.depot_id)
    
    # Remove empty routes
    routes = [route for route in routes if len(route) > 1]
    
    return {"routes": routes, "metadata": {}}