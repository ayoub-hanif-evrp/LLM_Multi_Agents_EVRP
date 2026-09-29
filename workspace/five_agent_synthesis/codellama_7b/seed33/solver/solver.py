import random

from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed, time_limit_s):
    # Initialize the random seed
    random.seed(seed)

    # Initialize the routes for each vehicle
    routes = [[] for _ in range(instance.n_vehicles)]

    # Loop through each customer and assign it to a vehicle
    for customer in instance.customers:
        # Find the closest vehicle to the customer
        closest_vehicle = None
        closest_distance = float('inf')
        for vehicle in instance.vehicles:
            distance_to_vehicle = distance(vehicle.depot, customer)
            if distance_to_vehicle < closest_distance:
                closest_distance = distance_to_vehicle
                closest_vehicle = vehicle

        # Add the customer to the route of the closest vehicle
        routes[closest_vehicle.id].append(customer.id)

    # Loop through each vehicle and ensure that it respects the capacity and time windows constraints
    for vehicle in instance.vehicles:
        # Calculate the total energy required for the route
        total_energy_required = 0
        for customer in routes[vehicle.id]:
            total_energy_required += energy_required(instance.node_map[customer], vehicle)

        # Check if the vehicle exceeds the capacity
        if total_energy_required > vehicle.capacity:
            # If the vehicle exceeds the capacity, remove the last customer from the route
            routes[vehicle.id].pop()

        # Check if the vehicle violates any time windows
        for customer in routes[vehicle.id]:
            if instance.customers[customer].time_window[0] > travel_time(vehicle.depot, instance.node_map[customer], vehicle):
                # If the vehicle violates a time window, remove the customer from the route
                routes[vehicle.id].remove(customer)

    # Return the routes for each vehicle
    return {"routes": routes}