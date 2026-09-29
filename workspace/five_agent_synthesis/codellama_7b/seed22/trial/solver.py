import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    # Initialize the random seed
    random.seed(seed)

    # Initialize the routes list
    routes = []

    # Initialize the current vehicle
    current_vehicle = instance.vehicle

    # Initialize the current route
    current_route = []

    # Initialize the current stop
    current_stop = instance.depot_id

    # Initialize the current battery level
    current_battery = current_vehicle.start_soc

    # Initialize the current time
    current_time = 0

    # Loop through all the customers
    for customer in instance.customers:
        # Check if the current vehicle is still valid
        if current_vehicle.capacity < customer.load:
            # If not, create a new vehicle
            current_vehicle = instance.vehicle
            current_route = []
            current_stop = instance.depot_id
            current_battery = current_vehicle.start_soc
            current_time = 0

        # Add the current stop to the current route
        current_route.append(customer.id)

        # Update the current battery level
        current_battery -= energy_required(instance.node_map[customer.id], current_vehicle)

        # Update the current time
        current_time += travel_time(instance.node_map[customer.id], current_vehicle)

        # If the current battery level is below the minimum, create a new vehicle
        if current_battery < current_vehicle.battery_capacity:
            current_vehicle = instance.vehicle
            current_route = []
            current_stop = instance.depot_id
            current_battery = current_vehicle.start_soc
            current_time = 0

        # If the current time is above the maximum, create a new vehicle
        if current_time > time_limit_s:
            current_vehicle = instance.vehicle
            current_route = []
            current_stop = instance.depot_id
            current_battery = current_vehicle.start_soc
            current_time = 0

    # Add the final stop to the current route
    current_route.append(instance.depot_id)

    # Return the routes list
    return {"routes": routes, "metadata": {"time_limit_s": time_limit_s, "seed": seed}}