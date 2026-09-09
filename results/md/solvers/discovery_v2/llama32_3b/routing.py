import numpy as np
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, propagate_route
from evrptw_autolab.problem.types import EVRPTWInstance
from deap import base, creator, tools, algorithms

# Define the custom population class
class CustomPopulation(base.Pipeline):
    def __init__(self, instance, seed, time_limit_s):
        self.instance = instance
        self.seed = seed
        self.time_limit_s = time_limit_s
        super().__init__()

    def _init(self): 
        # Initialize the population size and the number of generations
        self.population_size = 100
        self.num_generations = 10

    def _evaluate(self, individuals):
        # Evaluate each individual in the population
        for individual in individuals:
            # Generate a random route using the genetic algorithm
            route = algorithms.varandic(1.0, (self.instance.depot_id, ), self.instance.customer_ids)

            # Calculate the fitness of the individual based on the route's feasibility and distance
            fitness = 1 / (len(route) * travel_time(self.instance, route[0], route[-1]))

            # Update the individual's fitness and route
            individual.fitness.values = [fitness,]
            individual.route = route

    def _mate(self, individuals):
        # Perform crossover between two individuals
        parent1, parent2 = random.sample(individuals, 2)
        child = tools.mate(parent1, parent2, self.instance.customer_ids)

        # Update the child's fitness and route
        child.fitness.values = [1 / (len(child) * travel_time(self.instance, child[0], child[-1])),]
        child.route = child

    def _mutate(self, individuals):
        # Perform mutation on an individual
        parent = random.choice(individuals)
        for i in range(len(parent.route)): 
            if np.random.rand() < 0.01: 
                parent.route[i] = algorithms.varandic(1.0, (self.instance.depot_id, ), self.instance.customer_ids)[i]

    def _record(self, individuals):
        # Record the best individual in the population
        if len(individuals) > 0:
            best_individual = max(individuals, key=lambda x: x.fitness.values[0])
            return best_individual
