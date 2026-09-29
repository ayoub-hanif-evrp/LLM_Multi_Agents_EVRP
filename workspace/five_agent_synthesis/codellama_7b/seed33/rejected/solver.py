import random

from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import EVRPTWInstance, Node, StopState

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> dict:
    """
    Solve the EVRPTW problem using a routing-based architecture with charging and search components.

    Args:
        instance: The EVRPTW instance to solve.
        seed: The random seed to use for the search.
        time_limit_s: The time limit for the search, in seconds.

    Returns:
        A dictionary containing the routes and metadata for the solution.
    """
    # Set the random seed for reproducibility
    random.seed(seed)

    # Initialize the routes and metadata
    routes = []
    metadata = {}

    # Get the depot and customer nodes
    depot = instance.depot
    customers = instance.customers

    # Initialize the vehicle and its state
    vehicle = instance.vehicle
    state = StopState(
        battery_arrival=vehicle.start_soc,
        service_start=0,
        load=0,
        arrival_time=0
    )

    # Initialize the current route and its state
    current_route = [depot]
    current_state = state

    # Iterate over the customers
    for customer in customers:
        # Get the next customer and its state
        next_customer = customer
        next_state = StopState(
            battery_arrival=vehicle.start_soc,
            service_start=0,
            load=0,
            arrival_time=0
        )

        # Check if the current route is feasible
        if current_state.battery_arrival < next_customer.battery_required:
            # If the current route is not feasible, add it to the routes and reset the current route
            routes.append(current_route)
            current_route = [depot]
            current_state = state

        # Propagate the route and update the state
        propagated_route = propagate_route(instance, current_route + [next_customer])
        current_state = next_state

        # Add the next customer to the current route
        current_route += [next_customer]

    # Add the final route to the routes
    routes.append(current_route)

    # Return the routes and metadata
    return {"routes": routes, "metadata": metadata}