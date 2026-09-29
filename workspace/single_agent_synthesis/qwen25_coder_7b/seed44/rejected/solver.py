from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    import random
    random.seed(seed)

    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle

    # Initialize routes
    routes = []
    current_route = [depot_id]

    # Function to add a customer to the current route
    def add_customer(customer_id):
        nonlocal current_route
        customer = instance.node_map[customer_id]
        if energy_required(current_route[-1], customer, vehicle) <= vehicle.battery_departure:
            current_route.append(customer_id)
        else:
            routes.append(current_route)
            current_route = [depot_id, customer_id]

    # Add customers to routes
    for customer_id in customer_ids:
        add_customer(customer_id)

    # Add the final depot to the last route
    if current_route[-1] != depot_id:
        current_route.append(depot_id)
        routes.append(current_route)

    # Return the solution
    return {"routes": routes, "metadata": {}}