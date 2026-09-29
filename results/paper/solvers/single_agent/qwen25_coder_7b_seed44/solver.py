from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id]]
    
    # Function to add a customer to a route
    def add_customer_to_route(route, customer_id):
        route.append(customer_id)
        route.append(instance.depot_id)
    
    # Add customers to routes
    for customer_id in instance.customer_ids:
        add_customer_to_route(routes[0], customer_id)
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {}
    }