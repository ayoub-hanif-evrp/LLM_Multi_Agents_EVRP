from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution
from evrptw_autolab.problem.evaluator import first_fault
import random
import time

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    start_time = time.time()

    # Initialize population
    population = initialize_population(instance)

    while True:
        # Evaluate population
        population = evaluate_population(instance, population)

        # Select parents
        parents = select_parents(population)

        # Create children
        children = crossover(parents)

        # Mutate children
        children = mutate(children)

        # Replace population
        population = children

        # Check if time limit has been reached
        if time.time() - start_time > time_limit_s:
            break

    # Get the best solution
    best_solution = max(population, key=lambda x: (x.feasibility, len(x.routes), sum(distance(instance.node_map[a], instance.node_map[b]) for a, b in zip(x.routes, x.routes[1:]))))

    return {"routes": best_solution.routes, "metadata": {}}