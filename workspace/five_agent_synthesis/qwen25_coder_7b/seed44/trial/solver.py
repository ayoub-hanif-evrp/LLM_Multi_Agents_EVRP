import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    n_customers = instance.n_customers
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle
    capacity = vehicle.capacity
    battery_capacity = vehicle.battery_capacity
    consumption_rate = vehicle.consumption_rate
    velocity = vehicle.velocity
    inverse_refuel_rate = vehicle.inverse_refuel_rate
    start_soc = vehicle.start_soc

    def is_feasible(route):
        current_load = 0
        current_battery = start_soc
        for node_id in route:
            if node_id == depot_id:
                continue
            node = instance.node_map[node_id]
            if current_load + node.demand > capacity:
                return False
            if current_battery < energy_required(instance.node_map[route[route.index(node_id) - 1]], node, vehicle):
                return False
            current_load += node.demand
            current_battery -= energy_required(instance.node_map[route[route.index(node_id) - 1]], node, vehicle)
        return True

    def evaluate(route):
        total_distance = 0
        current_load = 0
        current_battery = start_soc
        for node_id in route:
            if node_id == depot_id:
                continue
            node = instance.node_map[node_id]
            total_distance += distance(instance.node_map[route[route.index(node_id) - 1]], node)
            current_load += node.demand
            current_battery -= energy_required(instance.node_map[route[route.index(node_id) - 1]], node, vehicle)
        return total_distance

    def improve_initial_solution(instance):
        routes = [[] for _ in range(instance.n_customers + len(instance.stations))]
        customer_ids = list(instance.customer_ids)
        random.shuffle(customer_ids)
        for customer_id in customer_ids:
            route_index = random.randint(0, instance.n_customers + len(instance.stations) - 1)
            routes[route_index].append(customer_id)
        routes = [route for route in routes if route]
        return routes

    def local_search(route):
        best_route = route[:]
        best_distance = evaluate(route)
        for i in range(len(route) - 1):
            for j in range(i + 1, len(route)):
                if i == 0 or j == len(route) - 1:
                    continue
                new_route = route[:]
                new_route[i], new_route[j] = new_route[j], new_route[i]
                if is_feasible(new_route) and evaluate(new_route) < best_distance:
                    best_route = new_route
                    best_distance = evaluate(best_route)
        return best_route

    def genetic_algorithm(routes, population_size, generations):
        for _ in range(generations):
            new_routes = []
            for _ in range(population_size):
                parent1 = random.choice(routes)
                parent2 = random.choice(routes)
                child = parent1[:]
                for i in range(1, len(parent2) - 1):
                    if random.random() < 0.5:
                        child[i] = parent2[i]
                if is_feasible(child):
                    new_routes.append(child)
            routes = new_routes
        return routes

    initial_solution = improve_initial_solution(instance)
    feasible_routes = [route for route in initial_solution if is_feasible(route)]
    if not feasible_routes:
        feasible_routes = [route for route in initial_solution]
    best_route = min(feasible_routes, key=evaluate)

    for _ in range(100):
        local_route = local_search(best_route)
        if is_feasible(local_route) and evaluate(local_route) < evaluate(best_route):
            best_route = local_route

    final_routes = [route for route in initial_solution if is_feasible(route)]
    final_routes.append(best_route)
    final_routes = genetic_algorithm(final_routes, population_size=50, generations=100)

    return {
        "routes": final_routes,
        "metadata": {
            "best_distance": evaluate(best_route)
        }
    }