import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    def is_feasible(routes):
        candidate = CandidateSolution(routes=routes)
        fault = first_fault(instance, candidate)
        return fault["family"] == "OK"
    
    def initial_solution():
        routes = []
        current_route = [instance.depot_id]
        current_load = 0
        current_battery = instance.vehicle.start_soc
        current_time = 0
        
        for customer_id in instance.customer_ids:
            customer = instance.node_map[customer_id]
            if current_load + customer.demand > instance.vehicle.capacity:
                current_route.append(instance.depot_id)
                routes.append(current_route)
                current_route = [instance.depot_id]
                current_load = 0
                current_battery = instance.vehicle.start_soc
                current_time = 0
            
            travel = travel_time(instance.node_map[current_route[-1]], customer, instance.vehicle)
            energy = energy_required(instance.node_map[current_route[-1]], customer, instance.vehicle)
            
            if current_time + travel > customer.ready_time or current_battery - energy < 0:
                current_route.append(instance.depot_id)
                routes.append(current_route)
                current_route = [instance.depot_id]
                current_load = 0
                current_battery = instance.vehicle.start_soc
                current_time = 0
            
            current_route.append(customer_id)
            current_load += customer.demand
            current_battery -= energy
            current_time += travel + customer.service_time
        
        if current_route:
            current_route.append(instance.depot_id)
            routes.append(current_route)
        
        return routes
    
    def local_search(routes):
        # Simple local search: 2-opt
        improved = True
        while improved:
            improved = False
            for i in range(len(routes)):
                for j in range(len(routes[i]) - 2):
                    for k in range(j + 2, len(routes[i]) - 1):
                        new_route = routes[i][:j+1] + routes[i][j+1:k+1][::-1] + routes[i][k+1:]
                        new_routes = [r for r in routes if r != routes[i]] + [new_route]
                        if is_feasible(new_routes):
                            routes = new_routes
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
        return routes
    
    def genetic_algorithm():
        population_size = 10
        mutation_rate = 0.1
        generations = 100
        
        population = [initial_solution() for _ in range(population_size)]
        
        for generation in range(generations):
            fitness = [len(routes) + sum(distance(instance.node_map[routes[i][j]], instance.node_map[routes[i][j+1]]) for i in range(len(routes)) for j in range(len(routes[i]) - 1)) for routes in population]
            best_routes = population[fitness.index(min(fitness))]
            
            new_population = [best_routes]
            while len(new_population) < population_size:
                parent1, parent2 = random.sample(population, 2)
                child = []
                for i in range(len(parent1)):
                    if random.random() < 0.5:
                        child.append(parent1[i])
                    else:
                        child.append(parent2[i])
                
                if random.random() < mutation_rate:
                    i, j = random.sample(range(len(child)), 2)
                    child[i], child[j] = child[j], child[i]
                
                new_population.append(child)
            
            population = new_population
        
        return best_routes
    
    routes = initial_solution()
    routes = local_search(routes)
    routes = genetic_algorithm()
    
    return {"routes": routes, "metadata": {"algorithm": "Genetic Algorithm with Local Search"}}