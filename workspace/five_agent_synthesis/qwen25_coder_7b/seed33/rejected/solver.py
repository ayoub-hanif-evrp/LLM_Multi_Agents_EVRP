import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    n_customers = instance.n_customers
    customers = instance.customers
    vehicle = instance.vehicle
    battery_capacity = vehicle.battery_capacity
    consumption_rate = vehicle.consumption_rate
    velocity = vehicle.velocity
    inverse_refuel_rate = vehicle.inverse_refuel_rate
    start_soc = vehicle.start_soc

    def calculate_route_cost(route):
        total_distance = 0
        for i in range(len(route) - 1):
            total_distance += distance(instance.node_map[route[i]], instance.node_map[route[i + 1]])
        return total_distance

    def calculate_route_energy(route):
        total_energy = 0
        for i in range(len(route) - 1):
            total_energy += energy_required(instance.node_map[route[i]], instance.node_map[route[i + 1]], vehicle)
        return total_energy

    def calculate_route_battery(route):
        battery = start_soc
        for i in range(len(route) - 1):
            battery -= consumption_rate * travel_time(instance.node_map[route[i]], instance.node_map[route[i + 1]], vehicle)
        return battery

    def repair_route_with_battery(route):
        while True:
            route = [depot_id] + route + [depot_id]
            stop_states = propagate_route_with_charging(instance, route)
            battery_arrival = stop_states[-1].battery_departure
            if battery_arrival >= 0:
                return route
            else:
                route = initialize_routes()[0]

    def repair_routes_with_battery(routes):
        return [repair_route_with_battery(route) for route in routes]

    def repair_solution_with_battery(routes):
        return {"routes": repair_routes_with_battery(routes), "metadata": {}}

    def solve_with_repair_and_battery(instance, seed, time_limit_s):
        routes = initialize_routes()
        return repair_solution_with_battery(routes)

    def initialize_routes():
        routes = [[] for _ in range(n_customers)]
        for customer in customers:
            routes[random.randint(0, n_customers - 1)].append(customer.id)
        routes = [[depot_id] + route + [depot_id] for route in routes]
        return routes

    def propagate_route_with_charging(instance, route):
        stop_states = []
        battery = start_soc
        for i in range(len(route) - 1):
            start_node = instance.node_map[route[i]]
            end_node = instance.node_map[route[i + 1]]
            energy_used = energy_required(start_node, end_node, vehicle)
            battery -= energy_used
            if battery < 0:
                station_id = find_nearest_station(instance, start_node)
                stop_state = propagate_route(instance, [station_id])[0]
                battery = full_recharge(vehicle, stop_state.battery_departure).battery_departure
            stop_state = propagate_route(instance, [route[i], route[i + 1]])[1]
            stop_states.append(stop_state)
        return stop_states

    def find_nearest_station(instance, node):
        nearest_station = None
        min_distance = float('inf')
        for station in instance.stations:
            distance_to_station = distance(node, station)
            if distance_to_station < min_distance:
                min_distance = distance_to_station
                nearest_station = station.id
        return nearest_station

    if "first_fault" in locals():
        return solve_with_repair_and_battery(instance, seed, time_limit_s)

    return {"routes": initialize_routes(), "metadata": {}}