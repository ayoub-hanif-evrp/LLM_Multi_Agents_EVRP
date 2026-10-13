from evrptw_autolab.problem.physics import distance, travel_time, energy_required, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    # Set the seed for the random number generator
    random.seed(seed)

    # Initialize routes
    routes = []

    # Generate random routes
    for _ in range(instance.n_customers):
        route = [instance.depot_id] + random.sample(instance.customer_ids, instance.n_customers) + [instance.depot_id]
        routes.append(route)

    # Return a dictionary with the routes and metadata
    return {
        "routes": routes,
        "metadata": {}
    }