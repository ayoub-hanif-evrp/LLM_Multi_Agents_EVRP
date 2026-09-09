import random
from evrptw_autolab.problem import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float) -> dict:
    """
    Solve the VRPTW problem using a random search algorithm.

    Args:
        instance (evrptw_autolab.problem.Instance): The VRPTW instance to solve.
        seed (int): The random seed for the solver.
        time_limit_s (float): The time limit in seconds for the solver.

    Returns:
        dict: A dictionary containing the solution routes and metadata.
    """
    # Initialize the random seed
    random.seed(seed)

    # Create an empty list to store the routes
    routes = []

    # Loop until the time limit is reached or all customers have been visited
    while time_limit_s > 0 and len(routes) < instance.n_customers:
        # Select a random customer from the instance
        customer = random.choice(instance.customers)

        # Check if the customer has already been visited
        if customer not in routes:
            # Add the customer to the list of routes
            routes.append(customer)

    # Return the solution routes and metadata
    return {"routes": routes, "metadata": {"time_limit_s": time_limit_s}}