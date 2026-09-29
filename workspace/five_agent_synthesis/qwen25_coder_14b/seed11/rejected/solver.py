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
        unvisited = list(instance.customer_ids)
        random.shuffle(unvisited)
        current_route = [instance.depot_id]
        current_load = 0
        current_battery = instance.vehicle.start_soc
        
        for customer_id in unvisited:
            customer = instance.node_map[customer_id]
            if current_load + customer.demand > instance.vehicle.capacity:
                current_route.append(instance.depot_id)
                routes.append(current_route)
                current_route = [instance.depot_id]
                current_load = 0
                current_battery = full_recharge(instance.vehicle, current_battery)
            
            if current_battery - energy_required(instance.node_map[current_route[-1]], customer, instance.vehicle) < 0:
                current_route.append(instance.depot_id)
                routes.append(current_route)
                current_route = [instance.depot_id]
                current_load = 0
                current_battery = full_recharge(instance.vehicle, current_battery)
            
            current_route.append(customer_id)
            current_load += customer.demand
            current_battery -= energy_required(instance.node_map[current_route[-2]], customer, instance.vehicle)
        
        if current_route:
            current_route.append(instance.depot_id)
            routes.append(current_route)
        
        return routes
    
    def local_search(routes):
        improved = True
        while improved:
            improved = False
            for i in range(len(routes)):
                for j in range(len(routes[i]) - 2):
                    for k in range(j + 1, len(routes[i]) - 1):
                        routes[i][j+1], routes[i][k] = routes[i][k], routes[i][j+1]
                        if is_feasible(routes):
                            improved = True
                        else:
                            routes[i][j+1], routes[i][k] = routes[i][k], routes[i][j+1]
        return routes
    
    routes = initial_solution()
    routes = local_search(routes)
    
    visited_customers = set()
    for route in routes:
        for node_id in route:
            if node_id in instance.customer_ids:
                visited_customers.add(node_id)
    
    if len(visited_customers) != instance.n_customers:
        raise ValueError("Not all customers are visited exactly once.")
    
    if not is_feasible(routes):
        raise ValueError("Routes are not feasible.")
    
    return {"routes": routes, "metadata": {}}