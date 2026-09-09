# solver.py

import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot as the only node
    routes = [[instance.depot_id]]
    
    # Add customers to the route in a round-robin fashion
    for customer_id in instance.customer_ids:
        routes[0].append(customer_id)
    
    # Ensure the route ends at the depot
    routes[0].append(instance.depot_id)
    
    return {
        "routes": routes,
        "metadata": {}
    }