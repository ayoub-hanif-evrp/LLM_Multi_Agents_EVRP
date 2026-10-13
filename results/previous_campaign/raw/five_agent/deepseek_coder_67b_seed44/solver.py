from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)

    # Initialize the solution
    solution = {"routes": [], "metadata": {}}

    # Create a route for each customer
    for customer_id in instance.customer_ids:
        route = [instance.depot_id, customer_id, instance.depot_id]
        solution["routes"].append(route)

    return solution