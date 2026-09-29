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
        current_soc = start_soc
        current_time = 0
        for customer_id in route[1:-1]:
            customer = instance.node_map[customer_id]
            travel_time_to_customer = travel_time(instance.depot, customer, vehicle)
            energy_needed = energy_required(instance.depot, customer, vehicle)
            if current_soc - energy_needed < 0:
                return False
            current_soc -= energy_needed
            current_time += travel_time_to_customer
            if current_time > customer.time_window[1]:
                return False
        return True

    def evaluate(route):
        current_soc = start_soc
        current_time = 0
        total_distance = 0
        for customer_id in route[1:-1]:
            customer = instance.node_map[customer_id]
            travel_time_to_customer = travel_time(instance.depot, customer, vehicle)
            energy_needed = energy_required(instance.depot, customer, vehicle)
            current_soc -= energy_needed
            current_time += travel_time_to_customer
            total_distance += distance(instance.depot, customer)
        return total_distance

    def generate_initial_solution():
        routes = [[] for _ in range(n_customers)]
        for customer_id in customer_ids:
            customer = instance.node_map[customer_id]
            min_distance = float('inf')
            best_route_index = -1
            for i in range(n_customers):
                if routes[i] and is_feasible([depot_id] + routes[i] + [depot_id]):
                    distance_to_customer = distance(instance.node_map[routes[i][-1]], customer)
                    if distance_to_customer < min_distance:
                        min_distance = distance_to_customer
                        best_route_index = i
            if best_route_index == -1:
                routes[0].append(customer_id)
            else:
                routes[best_route_index].append(customer_id)
        return routes

    def local_search(route):
        best_route = route[:]
        best_distance = evaluate(route)
        for i in range(1, len(route) - 1):
            for j in range(i + 1, len(route) - 1):
                new_route = route[:]
                new_route[i], new_route[j] = new_route[j], new_route[i]
                if is_feasible(new_route):
                    new_distance = evaluate(new_route)
                    if new_distance < best_distance:
                        best_route = new_route
                        best_distance = new_distance
        return best_route

    def genetic_algorithm():
        population_size = 50
        population = [generate_initial_solution() for _ in range(population_size)]
        for _ in range(100):
            new_population = []
            for _ in range(population_size):
                parent1 = random.choice(population)
                parent2 = random.choice(population)
                child = crossover(parent1, parent2)
                child = mutate(child)
                if is_feasible(child):
                    new_population.append(child)
            population = new_population
        best_route = min(population, key=evaluate)
        return best_route

    def crossover(parent1, parent2):
        if len(parent1) > 2:
            point1 = random.randint(1, len(parent1) - 2)
            point2 = random.randint(1, len(parent2) - 2)
            child = parent1[:point1] + parent2[point1:point2] + parent1[point2:]
            return child
        return parent1

    def mutate(route):
        if len(route) > 2:
            point1 = random.randint(1, len(route) - 2)
            point2 = random.randint(1, len(route) - 2)
            route[point1], route[point2] = route[point2], route[point1]
            return route
        return route

    initial_solution = generate_initial_solution()
    local_search_solution = local_search(initial_solution)
    genetic_algorithm_solution = genetic_algorithm()
    best_solution = min([initial_solution, local_search_solution, genetic_algorithm_solution], key=evaluate)

    feasible_routes = [route for route in best_solution if is_feasible(route)]
    feasible_routes = ensure_depot_constraint(feasible_routes, depot_id)
    feasible_routes = ensure_battery_constraint(feasible_routes, instance, vehicle)

    return {"routes": feasible_routes, "metadata": {"algorithm": "Genetic Algorithm with Local Search and Battery Constraint"}}

def ensure_battery_constraint(routes, instance, vehicle):
    for i, route in enumerate(routes):
        current_soc = vehicle.start_soc
        for customer_id in route[1:-1]:
            customer = instance.node_map[customer_id]
            travel_time_to_customer = travel_time(instance.depot, customer, vehicle)
            energy_needed = energy_required(instance.depot, customer, vehicle)
            if current_soc - energy_needed < 0:
                return False
            current_soc -= energy_needed
            if current_soc < vehicle.battery_capacity * 0.1:  # Ensure at least 10% battery left
                return False
    return routes

def ensure_depot_constraint(routes, depot_id):
    for i, route in enumerate(routes):
        if route[0] != depot_id or route[-1] != depot_id:
            routes[i] = [depot_id] + route[1:-1] + [depot_id]
    return routes