from evrptw_autolab.problem.physics import distance, travel_time, energy_required, propagate_route
import random
def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    population_size = 50
    generations = 100
    mutation_rate = 0.05
    crossover_rate = 0.7

    def initialize_population(size):
        return [generate_random_route(instance) for _ in range(size)]

    def generate_random_route(instance):
        nodes = list(instance.customer_ids)
        random.shuffle(nodes)
        route = [instance.depot_id] + nodes + [instance.depot_id]
        return route

    def fitness(route, instance):
        total_distance = 0
        for i in range(len(route) - 1):
            total_distance += distance(instance.node_map[route[i]], instance.node_map[route[i+1]])
        return total_distance

    def selection(population, fitness_scores):
        selected_indices = random.sample(range(len(population)), len(population) // 2)
        return [population[i] for i in selected_indices]

    def crossover(parent1, parent2):
        point = random.randint(1, len(parent1) - 2)
        child = parent1[:point] + parent2[point:] + parent1[point+1:]
        return child

    def mutation(route, instance):
        for i in range(len(route) - 1):
            if random.random() < mutation_rate:
                j = random.randint(0, len(route) - 1)
                route[i], route[j] = route[j], route[i]
        return route

    population = initialize_population(population_size)
    for generation in range(generations):
        fitness_scores = [fitness(route, instance) for route in population]
        selected_routes = selection(population, fitness_scores)
        new_population = []
        while len(new_population) < population_size:
            parent1, parent2 = random.sample(selected_routes, 2)
            if random.random() < crossover_rate:
                child = crossover(parent1, parent2)
            else:
                child = parent1
            new_population.append(child)
        population = new_population
    best_route = min(population, key=lambda route: fitness(route, instance))
    return {"routes": [best_route], "metadata": {}}