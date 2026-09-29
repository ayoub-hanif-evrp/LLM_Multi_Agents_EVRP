from evrptw_autolab.problem.physics import distance, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    # Initialize the vehicle state
    vehicle = instance.vehicle
    vehicle.soc = vehicle.battery_capacity
    routes = []

    # Iterate over each customer
    for customer in instance.customers:
        # Calculate the energy required to reach the customer
        energy_req = energy_required(instance.depot, customer, vehicle)

        # Check if the vehicle has enough energy to reach the customer
        if vehicle.soc >= energy_req:
            # Update the vehicle state
            vehicle.soc -= energy_req
            vehicle.position = customer.position

            # Propagate the route
            route = propagate_route(instance, vehicle.position)

            # Append the route to the list of routes
            routes.append(route)

        # The vehicle needs to recharge at the station
        else:
            # Full recharge the vehicle
            vehicle.soc = full_recharge(vehicle, vehicle.soc)

    return {"routes": routes, "metadata": {}}