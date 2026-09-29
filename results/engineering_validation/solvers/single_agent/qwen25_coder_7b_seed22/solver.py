from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    import random
    random.seed(seed)

    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    vehicle = instance.vehicle

    # Initialize routes with the depot
    routes = [[depot_id] for _ in range(len(customers))]

    # Assign customers to routes
    for customer in customers:
        min_cost = float('inf')
        best_route_index = 0
        for i, route in enumerate(routes):
            if len(route) == 1:
                cost = distance(instance.node_map[route[-1]], customer) + distance(customer, instance.depot)
            else:
                cost = distance(instance.node_map[route[-1]], customer) + distance(customer, instance.node_map[route[0]])
            if cost < min_cost:
                min_cost = cost
                best_route_index = i
        routes[best_route_index].append(customer.id)
        routes[best_route_index].append(depot_id)

    # Check for feasibility
    for i, route in enumerate(routes):
        if len(route) > 1:
            states = propagate_route(instance, route)
            for state in states:
                if state.battery_arrival < 0 or state.arrival_time > instance.node_map[route[-2]].due_time:
                    return {"routes": routes, "metadata": {"error": "Feasibility issue"}}

    return {"routes": routes, "metadata": {}}