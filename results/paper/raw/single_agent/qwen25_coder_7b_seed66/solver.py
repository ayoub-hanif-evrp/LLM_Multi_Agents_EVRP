import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    station_ids = instance.station_ids
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle

    def build_routes():
        routes = []
        remaining_customers = list(customer_ids)
        while remaining_customers:
            route = [depot_id]
            current_node = depot_id
            while remaining_customers:
                next_node = random.choice(remaining_customers)
                if distance(instance.node_map[current_node], instance.node_map[next_node]) <= vehicle.battery_capacity / vehicle.consumption_rate:
                    route.append(next_node)
                    remaining_customers.remove(next_node)
                    current_node = next_node
                else:
                    break
            route.append(depot_id)
            routes.append(route)
        return routes

    def insert_charge(route):
        for i in range(1, len(route) - 1):
            if route[i] in station_ids:
                stop_states = propagate_route(instance, route[:i + 1])
                last_stop = stop_states[-1]
                if last_stop.battery_departure < vehicle.battery_capacity:
                    charge_decision = full_recharge(vehicle, last_stop.battery_departure)
                    route.insert(i + 1, route[i])
                    route.insert(i + 1, route[i])
                    i += 2
        return route

    routes = build_routes()
    for i, route in enumerate(routes):
        routes[i] = insert_charge(route)

    return {"routes": routes, "metadata": {}}

def build_routes():
    routes = []
    remaining_customers = list(instance.customer_ids)
    while remaining_customers:
        route = [depot_id]
        current_node = depot_id
        while remaining_customers:
            next_node = random.choice(remaining_customers)
            if distance(instance.node_map[current_node], instance.node_map[next_node]) <= vehicle.battery_capacity / vehicle.consumption_rate:
                route.append(next_node)
                remaining_customers.remove(next_node)
                current_node = next_node
            else:
                break
        route.append(depot_id)
        routes.append(route)
    return routes

