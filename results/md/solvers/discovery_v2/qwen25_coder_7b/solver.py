from random import seed, randint
import time
from evrptw_autolab.problem.types import EVRPTWInstance
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
def nearest_neighbor(instance):
    routes = []
    unvisited_customers = set(instance.customer_ids)
    current_depot = instance.depot_id

    while unvisited_customers:
        route = [current_depot]
        remaining_customers = list(unvisited_customers)

        while remaining_customers:
            nearest_customer = None
            min_distance = float('inf')

            for customer in remaining_customers:
                dist = distance(instance.node_map[current_depot], instance.node_map[customer])
                if dist < min_distance:
                    min_distance = dist
                    nearest_customer = customer

            route.append(nearest_customer)
            unvisited_customers.remove(nearest_customer)
            current_depot = nearest_customer

        route.append(current_depot)
        routes.append(route)

    return routes
def generate_random_routes(instance):
    routes = []
    unvisited_customers = set(instance.customer_ids)
    while unvisited_customers:
        start_node = instance.depot_id
        route = [start_node]
        remaining_customers = list(unvisited_customers)
        while remaining_customers:
            next_customer = None
            min_distance = float('inf')
            for customer in remaining_customers:
                dist = distance(instance.node_map[start_node], instance.node_map[customer])
                if dist < min_distance:
                    min_distance = dist
                    next_customer = customer
            route.append(next_customer)
            unvisited_customers.remove(next_customer)
            start_node = next_customer
        route.append(start_node)
        routes.append(route)
    return routes
def select_parents(population):
    # Tournament selection
    parents = []
    for _ in range(len(population) // 2):
        parent1, parent2 = population[randint(0, len(population)-1)], population[randint(0, len(population)-1)]
        if evaluate(parent1) > evaluate(parent2):
            parents.append(parent1)
        else:
            parents.append(parent2)
    return parents
def crossover(parents):
    offspring = []
    for i in range(len(parents) // 2):
        parent1, parent2 = parents[i], parents[len(parents)-i-1]
        child1, child2 = [], []
        for route in parent1:
            if randint(0, 1) == 0:
                child1.append(route)
            else:
                child2.append(route)
        offspring.extend([child1, child2])
    return offspring
def mutate(offspring):
    for i in range(len(offspring)):
        route = offspring[i]
        if randint(0, 1) == 0:
            # Swap mutation
            idx1, idx2 = randint(0, len(route)-1), randint(0, len(route)-1)
            route[idx1], route[idx2] = route[idx2], route[idx1]
    return offspring
def local_search(route, instance):
    for i in range(len(route) - 2):
        if distance(instance.node_map[route[i]], instance.node_map[route[i+2]]) < distance(instance.node_map[route[i]], instance.node_map[route[i+1]]) + distance(instance.node_map[route[i+1]], instance.node_map[route[i+3]]):
            route[i+1], route[i+2] = route[i+2], route[i+1]
def evaluate(route, instance):
    total_distance = 0
    for i in range(len(route) - 1):
        total_distance += distance(instance.node_map[route[i]], instance.node_map[route[i+1]])
    return total_distance
def calculate_total_distance(routes, instance):
    total_distance = 0
    for route in routes:
        total_distance += evaluate(route, instance)
    return total_distance
def solve(instance, seed: int, time_limit_s: float):
    seed(seed)
    start_time = time.time()

    # Initialize population with random routes
    population_size = 10
    population = [generate_random_routes(instance) for _ in range(population_size)]

    while (time.time() - start_time) < time_limit_s:
        # GA: Selection, Crossover, Mutation
        parents = select_parents(population)
        offspring = crossover(parents)
        offspring = mutate(offspring)

        # VNS: Local Search
        for route in offspring:
            local_search(route, instance)

        # Evaluate and replace the worst individual in the population
        population.sort(key=lambda x: evaluate(x, instance))
        population[-1] = generate_random_routes(instance)

    return {'routes': population[0], 'metadata': {'vehicles': len(population[0]), 'distance': calculate_total_distance(population[0], instance)}}