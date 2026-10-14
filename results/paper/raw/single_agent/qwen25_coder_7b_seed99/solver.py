import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    station_ids = [station.id for station in instance.stations]
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle

    def build_routes(customers, stations, vehicle):
        routes = []
        remaining_customers = set(customer_ids)
        while remaining_customers:
            route = [depot_id]
            current_capacity = vehicle.capacity
            current_battery = vehicle.battery_capacity * vehicle.start_soc
            while remaining_customers and current_capacity > 0 and current_battery > 0:
                next_customer = min(remaining_customers, key=lambda c: distance(instance.node_map[route[-1]], instance.node_map[c]))
                if energy_required(instance.node_map[route[-1]], instance.node_map[next_customer], vehicle) <= current_battery:
                    route.append(next_customer)
                    remaining_customers.remove(next_customer)
                    current_capacity -= customers[customer_ids.index(next_customer)].demand
                    current_battery -= energy_required(instance.node_map[route[-2]], instance.node_map[next_customer], vehicle)
                else:
                    break
            route.append(depot_id)
            routes.append(route)
        return routes

    routes = build_routes(customers, stations, vehicle)
    for i in range(len(routes)):
        routes[i] = insert_charge(routes[i], stations, vehicle)

    return {"routes": routes, "metadata": {}}

def insert_charge(route, stations, vehicle):
    for i in range(1, len(route) - 1):
        if route[i] in [station.id for station in stations]:
            states = propagate_route(instance, route[:i + 1])
            last_state = states[-1]
            if last_state.battery_departure < vehicle.battery_capacity * vehicle.start_soc:
                charge_decision = full_recharge(vehicle, last_state.battery_departure)
                route.insert(i + 1, route[i])
                states = propagate_route(instance, route[:i + 2])
                last_state = states[-1]
                if last_state.battery_departure >= vehicle.battery_capacity * vehicle.start_soc:
                    route.pop(i + 2)
                else:
                    route.pop(i + 1)
    return route

