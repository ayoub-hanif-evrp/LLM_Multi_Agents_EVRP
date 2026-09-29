from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    vehicle = instance.vehicle
    
    # Initialize routes
    routes = [[depot_id]]
    
    # Add customers to routes
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        if len(routes[-1]) + 1 > vehicle.capacity:
            routes.append([depot_id])
        routes[-1].append(customer_id)
    
    routes[-1].append(depot_id)
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {}
    }