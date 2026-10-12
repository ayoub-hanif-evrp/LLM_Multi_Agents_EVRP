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

    def repair_route(route):
        while True:
            route = [depot_id] + route + [depot_id]
            if calculate_route_cost(route) == 0:
                return route
            else:
                route = initialize_routes()[0]

    def repair_routes(routes):
        return [repair_route(route) for route in routes]

    def repair_solution(routes):
        return {"routes": repair_routes(routes), "metadata": {}}

    def solve_with_repair(instance, seed, time_limit_s):
        routes = initialize_routes()
        return repair_solution(routes)

    def initialize_routes():
        routes = [[] for _ in range(n_customers)]
        for customer in customers:
            routes[random.randint(0, n_customers - 1)].append(customer.id)
        routes = [[depot_id] + route + [depot_id] for route in routes]
        return routes

    if "first_fault" in locals():
        return solve_with_repair(instance, seed, time_limit_s)

    return {"routes": initialize_routes(), "metadata": {}}