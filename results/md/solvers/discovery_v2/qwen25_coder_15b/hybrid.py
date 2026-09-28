import random
from typing import List, Tuple
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.solver import solve

class HybridAlgorithm:
    def __init__(self, instance, seed: int, time_limit_s: float):
        self.instance = instance
        self.seed = seed
        self.time_limit_s = time_limit_s
        self.population_size = 100
        self.num_generations = 50
        self.crossover_rate = 0.8
        self.mutation_rate = 0.2
        self.fitness_function = solve

    def generate_route(self, vehicle_id: str) -> List[str]:
        route = [self.instance.depot_id]
        current_capacity = self.instance.vehicle.capacity
        for customer in self.instance.customers:
            if energy_required(customer, self.instance.customers[route[-1]], self.instance.vehicle) <= current_capacity:
                route.append(customer.id)
                current_capacity -= energy_required(customer, self.instance.customers[route[-1]], self.instance.vehicle)
            else:
                break
        route.append(self.instance.depot_id)
        return route

    def evaluate_route(self, route: List[str]) -> float:
        total_distance = 0.0
        for i in range(len(route) - 1):
            total_distance += distance(self.instance.customers[route[i]], self.instance.customers[route[i + 1]])
        return total_distance

    def crossover(self, parent1: List[str], parent2: List[str]) -> List[str]:
        if random.random() < self.crossover_rate:
            mid_point = random.randint(1, len(parent1) - 2)
            child1 = parent1[:mid_point] + parent2[mid_point:] + parent1[mid_point+1:]
            child2 = parent2[:mid_point] + parent1[mid_point:] + parent2[mid_point+1:]
        else:
            child1 = parent1
            child2 = parent2
        return child1, child2

    def mutate(self, route: List[str]) -> List[str]:
        if random.random() < self.mutation_rate:
            i = random.randint(1, len(route) - 2)
            j = random.randint(i + 1, len(route) - 1)
            route[i], route[j] = route[j], route[i]
        return route

    def select_parents(self, population: List[List[str]]) -> Tuple[List[str], List[str]]:
        fitness_scores = [self.evaluate_route(route) for route in population]
        total_fitness = sum(fitness_scores)
        probabilities = [score / total_fitness for score in fitness_scores]
        parents = random.choices(population, weights=probabilities, k=2)
        return parents

    def evolve(self, population: List[List[str]]) -> List[List[str]]:
        new_population = []
        while len(new_population) < self.population_size:
            parent1, parent2 = self.select_parents(population)
            child1, child2 = self.crossover(parent1, parent2)
            child1 = self.mutate(child1)
            child2 = self.mutate(child2)
            new_population.append(child1)
            new_population.append(child2)
        return new_population

    def solve(self):
        population = [self.generate_route(vehicle_id) for vehicle_id in range(len(self.instance.vehicle_ids))]
        for _ in range(self.num_generations):
            population = self.evolve(population)
        best_route = min(population, key=self.evaluate_route)
        return {'routes': best_route, 'metadata': {'feasibility': 'improve'}}