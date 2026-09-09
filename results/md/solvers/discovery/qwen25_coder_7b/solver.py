from random import seed, randint
import time
from evrptw_autolab.problem.types import EVRPTWInstance
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float):
    seed(seed)
    start_time = time.time()
    best_solution = None
    best_cost = float('inf')

    def evaluate(solution):
        total_distance = 0
        for route in solution:
            if len(route) > 1:
                total_distance += distance(instance.node_map[route[-2]], instance.node_map[route[-1]])
        return total_distance

    def local_search(solution):
        improved = True
        while improved:
            improved = False
            for i in range(len(solution)):
                for j in range(i + 1, len(solution)):
                    if len(solution[i]) > 2 and len(solution[j]) > 2:
                        for k in range(1, len(solution[i]) - 1):
                            for l in range(1, len(solution[j]) - 1):
                                new_solution = solution[:]
                                new_solution[i] = new_solution[i][:k] + new_solution[j][l:] + new_solution[i][k+1:]
                                new_solution[j] = new_solution[j][:l] + new_solution[i][k:k+1] + new_solution[j][l+1:]
                                if evaluate(new_solution) < evaluate(solution):
                                    solution = new_solution
                                    improved = True
        return solution

    def genetic_algorithm(population_size, max_generations):
        population = [[instance.depot_id] + [randint(0, len(instance.customer_ids) - 1) for _ in range(randint(2, len(instance.customer_ids)))] + [instance.depot_id] for _ in range(population_size)]

        for generation in range(max_generations):
            population = sorted(population, key=evaluate)
            if evaluate(population[0]) < best_cost:
                best_solution = population[0]
                best_cost = evaluate(best_solution)

            new_population = [population[0]]
            for _ in range(1, population_size):
                parent1, parent2 = population[randint(0, len(population) - 1)], population[randint(0, len(population) - 1)]
                child = parent1[:randint(1, len(parent1) - 2)] + parent2[randint(1, len(parent2) - 2):]
                new_population.append(child)

            population = new_population

        return best_solution

    solution = genetic_algorithm(50, 100)
    solution = local_search(solution)

    return {
        'routes': [solution],
        'metadata': {'cost': evaluate(solution)}
    }