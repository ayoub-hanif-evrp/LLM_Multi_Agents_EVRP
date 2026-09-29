from evrptw_autolab.problem.physics import distance, travel_time, energy_required, propagate_route
import random
import time

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)

    # Initialize population
    population = []
    for _ in range(100):  # 100 routes in the population
        route = [instance.depot_id] + random.sample(instance.customer_ids, instance.n_customers) + [instance.depot_id]
        population.append(route)

    # Fitness function
    def fitness(route):
        total_distance = 0
        total_time = 0
        total_energy = 0
        for i in range(1, len(route)):
            total_distance += distance(instance.node_map[route[i-1]], instance.node_map[route[i]])
            total_time += travel_time(instance.node_map[route[i-1]], instance.node_map[route[i]], instance.vehicle)
            total_energy += energy_required(instance.node_map[route[i-1]], instance.node_map[route[i]], instance.vehicle)
        return total_distance, total_time, total_energy

    # Genetic operators
    def selection(population):
        return random.choices(population, k=10)

    def crossover(parent1, parent2):
        split_point = random.randint(1, len(parent1)-1)
        child1 = parent1[:split_point] + parent2[split_point:]
        child2 = parent2[:split_point] + parent1[split_point:]
        return child1, child2

    def mutation(child):
        split_point = random.randint(1, len(child)-1)
        split_point2 = random.randint(1, len(child)-1)
        child[split_point], child[split_point2] = child[split_point2], child[split_point]
        return child

    # Main loop for the genetic algorithm
    start_time = time.time()
    while time.time() < start_time + time_limit_s:
        # Evaluate the fitness of each route in the population
        population = sorted(population, key=fitness)

        # Apply the genetic operators (selection, crossover, mutation) to generate the new population
        parents = selection(population)
        children = []
        for _ in range(50):  # 50 children in the new population
            parent1, parent2 = random.sample(parents, 2)
            child1, child2 = crossover(parent1, parent2)
            child1 = mutation(child1)
            child2 = mutation(child2)
            children.extend([child1, child2])

        population = children

    # Return the best route found
    return {"routes": population[0], "metadata": {"total_distance": fitness(population[0])[0]}}