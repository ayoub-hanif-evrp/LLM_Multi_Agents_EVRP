from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes
    routes = []
    
    # Add depot to each route
    for customer_id in instance.customer_ids:
        route = [instance.depot_id, customer_id, instance.depot_id]
        routes.append(route)
    
    # Return the initial solution
    return {
        "routes": routes,
        "metadata": {}
    }