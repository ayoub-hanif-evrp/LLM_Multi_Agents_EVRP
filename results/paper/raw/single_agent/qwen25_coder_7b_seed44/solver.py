import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    depot_id = get_depot_id(instance)
    customer_ids = instance.customer_ids
    station_ids = instance.station_ids
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle
    depot = instance.depot
    node_map = instance.node_map

    def insert_charge(route, station_id):
        for i in range(len(route) - 1):
            if route[i] in station_ids and route[i + 1] in station_ids:
                continue
            if route[i] in station_ids:
                route.insert(i + 1, station_id)
                return route
        route.append(station_id)
        return route

    def build_routes(customers, stations, vehicle):
        routes = []
        remaining_customers = list(customers)
        while remaining_customers:
            route = [depot_id]
            current_node = depot_id
            while remaining_customers:
                next_customer = min(remaining_customers, key=lambda c: distance(node_map[current_node], node_map[c.id]))
                if energy_required(node_map[current_node], node_map[next_customer.id], vehicle) <= vehicle.battery_capacity:
                    route.append(next_customer.id)
                    remaining_customers.remove(next_customer)
                    current_node = next_customer.id
                else:
                    break
            if len(route) > 1:
                route = insert_charge(route, random.choice(station_ids))
                routes.append(route)
            else:
                break
        return routes

    routes = build_routes(customers, stations, vehicle)
    # Ensure each route starts and ends at the depot
    for route in routes:
        if route[0] != depot_id:
            route.insert(0, depot_id)
        if route[-1] != depot_id:
            route.append(depot_id)
    return {"routes": routes, "metadata": {}}

def get_depot_id(instance):
    return instance.depot_id

def build_routes(customers, stations, vehicle):
    routes = []
    remaining_customers = list(customers)
    while remaining_customers:
        route = [depot_id]
        current_node = depot_id
        while remaining_customers:
            next_customer = min(remaining_customers, key=lambda c: distance(node_map[current_node], node_map[c.id]))
            if energy_required(node_map[current_node], node_map[next_customer.id], vehicle) <= vehicle.battery_capacity:
                route.append(next_customer.id)
                remaining_customers.remove(next_customer)
                current_node = next_customer.id
            else:
                break
        if len(route) > 1:
            route = insert_charge(route, random.choice(station_ids))
            routes.append(route)
        else:
            break
    return routes



