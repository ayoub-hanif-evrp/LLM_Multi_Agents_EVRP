from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    vehicle = instance.vehicle
    
    # Initialize routes with the depot
    routes = [[depot_id] for _ in range(len(customer_ids))]
    
    # Assign customers to routes
    for customer in customers:
        # Find the route with the least load
        min_load_route = min(routes, key=lambda route: sum(1 for c in instance.customers if c.id in route))
        min_load_route.append(customer.id)
        min_load_route.append(depot_id)
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {}
    }