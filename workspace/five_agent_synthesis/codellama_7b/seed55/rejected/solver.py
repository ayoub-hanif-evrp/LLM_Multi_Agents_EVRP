import random

from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import EVRPTWInstance, Node, StopState

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> dict:
    """Complete executable solver for EVRPTW.

    Args:
        instance (EVRPTWInstance): The instance of the problem.
        seed (int): The seed for the random number generator.
        time_limit_s (float): The time limit for the solve.

    Returns:
        dict: The solution dictionary.
    """
    random.seed(seed)

    # Initialize the vehicle and set its starting state
    vehicle = instance.vehicle
    vehicle.battery_soc = vehicle.start_soc

    # Initialize the routes and the starting state of the vehicle
    routes = []
    for customer in instance.customers:
        route = [instance.depot_id]
        route.append(customer.id)
        route.append(instance.depot_id)
        routes.append(route)

    # Iterate over the time limit
    start_time = 0
    end_time = 0
    while end_time < time_limit_s:
        # Choose a route to visit
        route_index = random.choice(range(len(routes)))
        route = routes[route_index]

        # Choose a node to visit
        node_index = random.choice(range(len(route) - 1))
        node = route[node_index]

        # Update the vehicle state
        vehicle.battery_soc = full_recharge(vehicle, vehicle.battery_soc)
        vehicle.battery_soc = energy_required(instance.node_map[node], vehicle)
        vehicle.battery_soc = min(vehicle.battery_soc, vehicle.battery_capacity)

        # Update the route state
        route[node_index + 1] = instance.node_map[node].id

        # Update the end time
        end_time = start_time + travel_time(instance.node_map[node], vehicle)

    # Return the routes and metadata
    return {"routes": routes, "metadata": {"feasibility": "improve", "vehicles": "reduce"}}