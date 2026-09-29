from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def fix_battery_at_stations(routes, instance):
    for route in routes:
        stops = propagate_route(instance, route)
        for stop in stops:
            if stop.load == 'station':
                stop.battery_arrival = full_recharge(instance.vehicle, stop.battery_arrival)
    return routes

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)

    # Initialize routes with the depot
    routes = [[instance.depot_id]]

    # Assign customers to routes
    for customer_id in instance.customer_ids:
        min_distance = float('inf')
        best_route_index = -1
        for i, route in enumerate(routes):
            if len(route) == 1:
                dist = distance(instance.node_map[route[0]], instance.node_map[customer_id])
            else:
                dist = distance(instance.node_map[route[-2]], instance.node_map[customer_id])
            if dist < min_distance:
                min_distance = dist
                best_route_index = i
        routes[best_route_index].append(customer_id)

    # Add depot to the end of each route
    for i in range(len(routes)):
        routes[i].append(instance.depot_id)

    # Full charge at stations for each route
    routes = fix_battery_at_stations(routes, instance)

    return {"routes": routes, "metadata": {}}