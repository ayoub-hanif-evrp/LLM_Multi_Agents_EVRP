from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    # Initialize the random seed
    random.seed(seed)

    # Initialize the solution
    routes = [[] for _ in range(instance.vehicle.capacity)]
    current_vehicle = 0
    current_capacity = [0] * instance.vehicle.capacity

    # Sort customers by their demand
    customers = sorted(instance.customers, key=lambda c: c.demand)

    # Assign customers to vehicles
    for customer in customers:
        if (current_capacity[current_vehicle] + customer.demand <= instance.vehicle.capacity and
            customer.time_window[0] <= instance.current_time <= customer.time_window[1]):
            routes[current_vehicle].append(customer.id)
            current_capacity[current_vehicle] += customer.demand
            current_vehicle = (current_vehicle + 1) % instance.vehicle.capacity

    # Add depot to the end of each route
    for route in routes:
        route.append(instance.depot_id)

    return {"routes": routes, "metadata": {}}