import random

from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import EVRPTWInstance, Node, StopState

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> dict:
    """
    Solve the EVRPTW instance using a hybrid routing-based and charging-based algorithm.

    Args:
        instance: The EVRPTW instance to solve.
        seed: The random seed to use for the search.
        time_limit_s: The time limit in seconds for the search.

    Returns:
        The solution dictionary with the routes and metadata.
    """
    # Initialize the random seed
    random.seed(seed)

    # Initialize the routes and metadata
    routes = []
    metadata = {
        "feasibility": "unknown",
        "vehicles": "unknown",
        "distance": "unknown"
    }

    # Initialize the charging-based algorithm
    charging_algorithm = ChargingAlgorithm(instance)

    # Initialize the routing-based algorithm
    routing_algorithm = RoutingAlgorithm(instance)

    # Run the charging-based algorithm
    charging_algorithm.run(time_limit_s)

    # Run the routing-based algorithm
    routing_algorithm.run(time_limit_s)

    # Combine the results of the two algorithms
    routes = charging_algorithm.routes + routing_algorithm.routes
    metadata["feasibility"] = "improved" if charging_algorithm.feasibility > routing_algorithm.feasibility else "same"
    metadata["vehicles"] = "reduced" if len(charging_algorithm.routes) < len(routing_algorithm.routes) else "same"
    metadata["distance"] = "improved" if charging_algorithm.distance > routing_algorithm.distance else "same"

    # Return the solution dictionary
    return {
        "routes": routes,
        "metadata": metadata
    }