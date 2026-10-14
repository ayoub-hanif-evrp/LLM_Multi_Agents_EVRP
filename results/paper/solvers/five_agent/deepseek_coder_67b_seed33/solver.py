from typing import List, Tuple
from evrptw_autolab.problem.types import EVRPTWInstance, Node
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> dict:
    # Set the seed for the random number generator
    random.seed(seed)

    # Initialize the solution
    solution = {"routes": [], "metadata": {}}

    # Create routes for each customer
    for customer in instance.customers:
        route = [instance.depot_id, customer.id, instance.depot_id]
        solution["routes"].append(route)

    # Insert charging stations where necessary
    for station in instance.stations:
        if station.id not in solution["routes"][0] and station.id not in solution["routes"][-1]:
            solution["routes"].insert(1, [station.id])

    return solution