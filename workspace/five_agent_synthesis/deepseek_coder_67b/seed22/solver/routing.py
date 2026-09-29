from evrptw_autolab.problem.physics import distance, travel_time, energy_required, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution
import random

def solve(instance, seed: int, time_limit_s: float):
    # Set the seed for the random number generator
    random.seed(seed)

    # Initialize the population
    population = [instance.depot_id] + random.sample(instance.customer_ids, instance.n_customers) + [instance.depot_id]
    best_solution = (float('inf'), [])

    while time_limit_s > 0:
        # Evaluate the population
        for individual in population:
            routes = [individual[i:i+instance.vehicle.capacity] for i in range(0, len(individual), instance.vehicle.capacity)]
            candidate_solution = CandidateSolution(routes=routes)
            fault = first_fault(instance, candidate_solution)
            if fault["family"] == "OK":
                feasibility = len(routes)
                vehicles = len(routes)
                total_distance = sum(distance(individual[i], individual[i+1]) for i in range(len(individual) - 1))
                if feasibility < best_solution[0]:
                    best_solution = (feasibility, routes)
            else:
                continue

        # Update the population
        population = list(best_solution[1])

        # Update the time limit
        time_limit_s -= 1

    return {"routes": best_solution[1], "metadata": {}}