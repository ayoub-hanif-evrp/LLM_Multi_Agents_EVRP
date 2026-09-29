from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    n_customers = instance.n_customers
    customers = instance.customers
    depot = instance.depot
    vehicle = instance.vehicle
    
    # Initialize routes
    routes = [[depot_id]]
    
    # Visit each customer in a random order
    for customer_id in random.sample(customer_ids, n_customers):
        routes[-1].append(customer_id)
    
    # Add the depot to the end of the route
    routes[-1].append(depot_id)
    
    return {
        "routes": routes,
        "metadata": {}
    }