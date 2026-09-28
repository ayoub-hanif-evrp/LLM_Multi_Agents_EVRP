import evrptw_autolab.problem.types
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random
import numpy as np
import operator
import math
import time
import datetime
import os
import sys
import itertools
import heapq
import functools
import bisect
import collections
import copy
import inspect
from typing import List, Tuple, Dict
from evrptw_autolab.problem.types import EVRPTWInstance
from evrptw_autolab.problem.physics import VehicleSpec
class Solve:
    def __init__(self, instance: EVRPTWInstance, seed: int, time_limit_s: float):
        self.instance = instance
        self.seed = seed
        self.time_limit_s = time_limit_s
        self.population_size = 100
        self.iterations = 100
        self.mutation_rate = 0.1
        self.crossover_rate = 0.5
    def generate_initial_population(self) -> List[List[str]]:
        # Initialize the population with random routes
        population = []
        for _ in range(self.population_size):
            route = [self.instance.depot_id]
            while len(route) < self.instance.n_customers:
                node_id = random.choice(list(self.instance.customer_ids))
                route.append(node_id)
                if node_id != self.instance.depot_id:
                    break
            population.append(route)
        return population
    def evaluate_population(self, population: List[List[str]]) -> Dict[str, float]:
        # Evaluate the fitness of each route in the population
        fitness = {}
        for i, route in enumerate(population):
            distance = 0
            time = 0
            energy = 0
            for j in range(len(route) - 1):
                node_id1 = self.instance.node_map[route[j]]
                node_id2 = self.instance.node_map[route[j + 1]]
                distance += distance(node_id1, node_id2)
                time += travel_time(node_id1, node_id2, self.instance.vehicle)
                energy += energy_required(node_id1, node_id2, self.instance.vehicle)
            fitness[f'route_{i}'] = (distance / self.instance.n_customers) + (time / self.instance.n_customers) + (energy / self.instance.n_customers)
        return fitness
    def mutate_route(self, route: List[str]) -> List[str]:
        # Mutate a route by swapping two nodes
        if random.random() < self.mutation_rate:
            i = random.randint(0, len(route) - 1)
            j = random.randint(0, len(route) - 1)
            route[i], route[j] = route[j], route[i]
        return route
    def crossover_route(self, parent: List[str], child: List[str]) -> List[str]:
        # Crossover two routes by taking the middle part of each route
        if random.random() < self.crossover_rate:
            i = random.randint(0, len(parent) - 1)
            j = random.randint(0, len(child) - 1)
            parent[i:j + 1], child[i:j + 1] = child[i:j + 1], parent[i:j + 1]
        return parent
    def generate_next_generation(self, population: List[List[str]]) -> List[List[str]]:
        # Generate the next generation by selecting the fittest routes and performing crossover and mutation
        fitness = self.evaluate_population(population)
        next_generation = []
        for _ in range(self.population_size):
            parent1 = random.choice(list(fitness.keys()))
            parent2 = random.choice(list(fitness.keys()))
            child = self.crossover_route(parent1, parent2)
            child = self.mutate_route(child)
            next_generation.append(child)
        return next_generation
    def solve(self) -> Dict[str, List[List[str]]]:
        # Solve the problem by iterating over the generations
        population = self.generate_initial_population()
        for _ in range(self.iterations):
            population = self.generate_next_generation(population)
        fitness = self.evaluate_population(population)
        return {'routes': [route for route, _ in sorted(fitness.items(), key=lambda x: x[1])], 'metadata': {}}
