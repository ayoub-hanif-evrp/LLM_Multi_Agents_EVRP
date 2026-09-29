from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle
    
    # Initialize routes with the depot
    routes = [[depot_id] for _ in range(len(customers) + 1)]
    
    # Assign customers to routes
    for customer in customers:
        best_route = None
        best_cost = float('inf')
        
        for route in routes:
            if len(route) == 1:
                cost = distance(instance.node_map[depot_id], instance.node_map[customer.id]) + distance(instance.node_map[customer.id], instance.node_map[depot_id])
            else:
                cost = distance(instance.node_map[route[-1]], instance.node_map[customer.id])
            
            if cost < best_cost:
                best_cost = cost
                best_route = route
        
        best_route.append(customer.id)
    
    # Add depot to the end of each route
    for route in routes:
        route.append(depot_id)
    
    # Return the solution
    return {"routes": routes, "metadata": {}}