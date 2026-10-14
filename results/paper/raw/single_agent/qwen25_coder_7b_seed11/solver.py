import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    station_ids = instance.station_ids
    depot = instance.depot
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle

    # Initialize routes
    routes = [[depot_id] for _ in range(len(customers) + 1)]
    customer_index = 0

    while customer_index < len(customers):
        current_depot = depot_id
        current_route = [current_depot]
        current_load = 0
        current_battery = vehicle.start_soc

        while customer_index < len(customers) and current_load + customers[customer_index].demand <= vehicle.capacity:
            current_load += customers[customer_index].demand
            current_route.append(customers[customer_index].id)
            customer_index += 1

        current_route.append(current_depot)
        routes.append(current_route)

    # Insert charging stations
    for i in range(len(routes)):
        if len(routes[i]) > 2:
            for j in range(1, len(routes[i]) - 1):
                if routes[i][j] in station_ids:
                    continue
                if energy_required(instance.node_map[routes[i][j-1]], instance.node_map[routes[i][j]], vehicle) > vehicle.battery_capacity * vehicle.start_soc:
                    routes[i].insert(j, routes[i][j-1])
                    break

    # Ensure depot is at the end of each route
    for i in range(len(routes)):
        if routes[i][-1] != depot_id:
            routes[i].append(depot_id)

    # Remove empty routes
    routes = [route for route in routes if len(route) > 1]

    return {
        "routes": routes,
        "metadata": {}
    }

