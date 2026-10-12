from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution
from evrptw_autolab.problem.evaluator import first_fault
import random

def solve(instance, seed: int, time_limit_s: float):
    # Set the seed for the random number generator
    random.seed(seed)

    # Initialize the routes
    routes = []

    # Sort the customers by due date
    sorted_customers = sorted(instance.customers, key=lambda customer: customer.due_time)

    # For each customer
    for customer in sorted_customers:
        # Try to find a route that can serve the customer
        for route in routes:
            if route[-1].due_time + distance(route[-1], customer) <= customer.due_time:
                route.append(customer)
                break
        else:
            # If no route can serve the customer, create a new one
            routes.append([instance.depot, customer, instance.depot])

    # Return the routes and metadata
    return {
        "routes": [list(map(lambda node: node.id, route)) for route in routes],
        "metadata": {}
    }