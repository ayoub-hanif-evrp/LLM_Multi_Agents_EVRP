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

    def build_routes():
        routes = []
        remaining_customers = list(customer_ids)
        while remaining_customers:
            route = [depot_id]
            current_node = depot_id
            while remaining_customers:
                next_node = min(remaining_customers, key=lambda c: distance(instance.node_map[current_node], instance.node_map[c]))
                route.append(next_node)
                remaining_customers.remove(next_node)
                current_node = next_node
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
                    return route
        return route

    def check_time_windows(route):
        for i in range(1, len(route) - 1):
            stop_states = propagate_route(instance, route[:i + 1])
            last_stop = stop_states[-1]
            if last_stop.arrival_time < instance.node_map[route[i]].ready_time or last_stop.arrival_time > instance.node_map[route[i]].due_time:
                return False
        return True

    def check_battery_capacity(route):
        for i in range(1, len(route) - 1):
            stop_states = propagate_route(instance, route[:i + 1])
            last_stop = stop_states[-1]
            if last_stop.battery_departure < 0:
                return False
        return True

    routes = build_routes()
    for i in range(len(routes)):
        routes[i] = insert_charge(routes[i])
        if not check_time_windows(routes[i]) or not check_battery_capacity(routes[i]):
            routes[i] = [depot_id] * (len(routes[i]) + 2)

    return {"routes": routes, "metadata": {}}

