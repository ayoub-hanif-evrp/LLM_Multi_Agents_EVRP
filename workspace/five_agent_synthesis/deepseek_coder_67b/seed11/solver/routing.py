import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)

    # Initialize population
    population = []
    for _ in range(100):   # population size
        individual = [instance.depot_id] + random.sample(instance.customer_ids, instance.n_customers) + [instance.depot_id]
        population.append(individual)

    # Evaluate initial population
    fitness = []
    for individual in population:
        total_distance = sum(distance(instance.node_map[individual[i]], instance.node_map[individual[i+1]]) for i in range(len(individual) - 1))
        total_energy = sum(energy_required(instance.node_map[individual[i]], instance.node_map[individual[i+1]], instance.vehicle) for i in range(len(individual) - 1))
        total_time = sum(travel_time(instance.node_map[individual[i]], instance.node_map[individual[i+1]], instance.vehicle) for i in range(len(individual) - 1))
        fitness.append((total_distance, total_energy, total_time))

    # Start PSO (Particle Swarm Optimization)
    for _ in range(100):   # number of iterations
        for i, individual in enumerate(population):
            # Select two random individuals
            a, b = random.sample(range(len(population)), 2)
            # Update velocity
            for j in range(len(individual) - 1):
                individual[j+1] = individual[j+1] + (instance.node_map[individual[j+1]].position - instance.node_map[individual[j]].position) + (instance.node_map[population[a][j+1]].position - instance.node_map[population[a][j]].position) + (instance.node_map[population[b][j+1]].position - instance.node_map[population[b][j]].position)
            # Update position
            for j in range(len(individual) - 1):
                individual[j+1] = instance.node_map[individual[j+1]].position + individual[j+1]
            # Evaluate new individual
            total_distance = sum(distance(instance.node_map[individual[i]], instance.node_map[individual[i+1]]) for i in range(len(individual) - 1))
            total_energy = sum(energy_required(instance.node_map[individual[i]], instance.node_map[individual[i+1]], instance.vehicle) for i in range(len(individual) - 1))
            total_time = sum(travel_time(instance.node_map[individual[i]], instance.node_map[individual[i+1]], instance.vehicle) for i in range(len(individual) - 1))
            fitness[i] = (total_distance, total_energy, total_time)

    # Return best individual
    best_individual = min(fitness)
    return {"routes": [best_individual], "metadata": {}}