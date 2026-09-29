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
        current_battery = instance.vehicle.start_soc
        current_time = 0
        
        for customer_id in instance.customer_ids:
            customer = instance.node_map[customer_id]
            if current_load + customer.demand > instance.vehicle.capacity:
                routes.append(current_route + [instance.depot_id])
                current_route = [instance.depot_id]
                current_load = 0
                current_battery = instance.vehicle.start_soc
                current_time = 0
            
            if current_battery - energy_required(instance.node_map[current_route[-1]], customer, instance.vehicle) < 0:
                routes.append(current_route + [instance.depot_id])
                current_route = [instance.depot_id]
                current_load = 0
                current_battery = instance.vehicle.start_soc
                current_time = 0
            
            arrival_time = current_time + travel_time(instance.node_map[current_route[-1]], customer, instance.vehicle)
            if arrival_time < customer.ready_time:
                current_time = customer.ready_time
            elif arrival_time > customer.due_time:
                return None
            
            current_time += customer.service_time
            current_load += customer.demand
            current_battery -= energy_required(instance.node_map[current_route[-1]], customer, instance.vehicle)
            current_route.append(customer_id)
        
        if current_route:
            routes.append(current_route + [instance.depot_id])
        
        return routes
    
    def local_search(routes):
        # Implement a simple local search to improve the solution
        # This is a placeholder for more sophisticated local search strategies
        return routes
    
    def construct_solution():
        initial = initial_solution()
        if initial is None:
            return None
        return local_search(initial)
    
    best_routes = None
    best_metadata = {"feasible": False, "vehicles": float('inf'), "distance": float('inf')}
    
    start_time = time.time()
    while time.time() - start_time < time_limit_s:
        candidate_routes = construct_solution()
        if candidate_routes is None:
            continue
        
        if is_feasible(candidate_routes):
            candidate_metadata = {
                "feasible": True,
                "vehicles": len(candidate_routes),
                "distance": sum(distance(instance.node_map[r[i]], instance.node_map[r[i+1]]) for r in candidate_routes for i in range(len(r)-1))
            }
            
            if candidate_metadata["vehicles"] < best_metadata["vehicles"] or \
               (candidate_metadata["vehicles"] == best_metadata["vehicles"] and candidate_metadata["distance"] < best_metadata["distance"]):
                best_routes = candidate_routes
                best_metadata = candidate_metadata
    
    if best_routes is None:
        return {"routes": [], "metadata": {}}
    
    return {"routes": best_routes, "metadata": best_metadata}