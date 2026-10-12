import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    # Initialize the random seed
    random.seed(seed)

    # Create a list of customers
    customers = [instance.node_map[node_id] for node_id in instance.customer_ids]

    # Sort customers by due time
    customers.sort(key=lambda customer: customer.due_time)

    # Initialize the list of routes
    routes = []

    # Initialize the current route
    current_route = [instance.depot_id]

    # Initialize the current capacity
    current_capacity = instance.vehicle.capacity

    # Initialize the current energy
    current_energy = instance.vehicle.battery_capacity

    # Initialize the current position
    current_position = instance.depot

    # Initialize the current time
    current_time = 0

    # Iterate over the customers
    for customer in customers:
        # Calculate the travel time to the customer
        travel_time_to_customer = travel_time(current_position, customer, instance.vehicle)

        # Check if the vehicle has enough energy to reach the customer
        if current_energy - travel_time_to_customer < 0:
            # If not, start a new route
            routes.append(current_route)
            current_route = [instance.depot_id]
            current_capacity = instance.vehicle.capacity
            current_energy = instance.vehicle.battery_capacity
            current_position = instance.depot
            current_time = 0

        # Check if the vehicle has enough capacity to accommodate the customer
        if current_capacity - customer.demand < 0:
            # If not, start a new route
            routes.append(current_route)
            current_route = [instance.depot_id]
            current_capacity = instance.vehicle.capacity
            current_energy = instance.vehicle.battery_capacity
            current_position = instance.depot
            current_time = 0

        # Add the customer to the current route
        current_route.append(customer.id)

        # Update the current capacity
        current_capacity -= customer.demand

        # Update the current energy
        current_energy -= travel_time_to_customer

        # Update the current position
        current_position = customer

        # Update the current time
        current_time += travel_time_to_customer

    # Add the last route to the list of routes
    routes.append(current_route)

    # Return the list of routes and an empty metadata dictionary
    return {"routes": routes, "metadata": {}}