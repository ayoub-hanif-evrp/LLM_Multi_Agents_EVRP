import random
import time
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
        current_battery = instance.vehicle.start_soc * instance.vehicle.battery_capacity
        
        for customer_id in instance.customer_ids:
            customer = instance.node_map[customer_id]
            if current_load + customer.demand > instance.vehicle.capacity:
                current_route.append(instance.depot_id)
                routes.append(current_route)
                current_route = [instance.depot_id]
                current_load = 0
                current_battery = full_recharge(instance.vehicle, current_battery)
            
            if current_battery < energy_required(customer, instance.depot, instance.vehicle):
                current_route.append(instance.depot_id)
                routes.append(current_route)
                current_route = [instance.depot_id]
                current_battery = full_recharge(instance.vehicle, current_battery)
            
            current_route.append(customer_id)
            current_load += customer.demand
            current_battery -= energy_required(customer, instance.depot, instance.vehicle)
        
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
                for j in range(i + 1, len(routes)):
                    for k in range(1, len(routes[i]) - 1):
                        for l in range(1, len(routes[j]) - 1):
                            new_routes = routes[:]
                            new_routes[i] = new_routes[i][:k] + new_routes[j][l:k+1] + new_routes[i][k+1:]
                            new_routes[j] = new_routes[j][:l] + new_routes[i][k:l+1] + new_routes[j][l+1:]
                            if is_feasible(new_routes):
                                routes = new_routes
                                improved = True
                                break
                        if improved:
                            break
                    if improved:
                        break
                if improved:
                    break
        return routes
    
    def construct_solution():
        initial_routes = initial_solution()
        feasible_routes = local_search(initial_routes)
        return feasible_routes
    
    start_time = time.time()
    best_routes = construct_solution()
    
    while time.time() - start_time < time_limit_s:
        new_routes = construct_solution()
        if is_feasible(new_routes) and len(new_routes) < len(best_routes):
            best_routes = new_routes
    
    return {"routes": best_routes, "metadata": {}}