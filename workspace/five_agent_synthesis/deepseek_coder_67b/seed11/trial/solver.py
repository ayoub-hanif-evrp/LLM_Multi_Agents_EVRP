from deap import base, creator, tools, algorithms
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution
from evrptw_autolab.problem.evaluator import first_fault
import random
import numpy as np

# Define the fitness function
def fitness(individual):
    routes = [individual[i:i+instance.n_customers] for i in range(0, len(individual), instance.n_customers)]
    candidate_solution = CandidateSolution(routes=routes)
    packet = first_fault(instance, candidate_solution)
    if packet["family"] == "OK":
        return len(routes), -sum(distance(instance.node_map[a], instance.node_map[b]) for a, b in zip(individual, individual[1:])),
    else:
        return 0, 0

# Define the genetic algorithm
def solve(instance, seed, time_limit_s):
    # Set the random seed
    random.seed(seed)

    # Define the individual
    creator.create("Fitness", base.Fitness, weights=(1.0, -1.0))
    creator.create("Individual", list, fitness=creator.Fitness)

    # Define the population
    toolbox = base.Toolbox()
    toolbox.register("individual", tools.initRepeat, creator.Individual, instance.n_customers, random.choice, instance.customer_ids)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    # Define the genetic operators
    toolbox.register("evaluate", fitness)
    toolbox.register("mate", tools.cxTwoPoint)
    toolbox.register("mutate", tools.mutShuffleIndexes, indpb=0.05)
    toolbox.register("select", tools.selTournament, tournsize=3)

    # Run the genetic algorithm
    pop = toolbox.population(n=100)
    hof = tools.HallOfFame(1)
    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("avg", np.mean)
    stats.register("min", np.min)
    stats.register("max", np.max)

    algorithms.eaSimple(pop, toolbox, cxpb=0.5, mutpb=0.2, ngen=100, stats=stats, halloffame=hof, verbose=True)

    return {"routes": hof[0], "metadata": {}}