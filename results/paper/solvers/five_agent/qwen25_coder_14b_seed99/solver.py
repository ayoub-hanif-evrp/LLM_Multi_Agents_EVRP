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
            
            if current_battery < energy_required(customer, instance.depot, instance.vehicle):
                routes.append(current_route + [instance.depot_id])
                current_route = [instance.depot_id]
                current_load = 0
                current_battery = instance.vehicle.start_soc
                current_time = 0
            
            travel = travel_time(instance.node_map[current_route[-1]], customer, instance.vehicle)
            if current_time + travel < customer.ready_time:
                current_time = customer.ready_time
            
            current_time += travel
            current_battery -= energy_required(instance.node_map[current_route[-1]], customer, instance.vehicle)
            current_route.append(customer_id)
            current_load += customer.demand
            current_time += customer.service_time
        
        if current_route:
            routes.append(current_route + [instance.depot_id])
        
        return routes
    
    def local_search(routes):
        # Implement a simple local search to improve the solution
        # This is a placeholder for more sophisticated local search strategies
        return routes
    
    initial_routes = initial_solution()
    if not is_feasible(initial_routes):
        raise ValueError("Initial solution is not feasible")
    
    best_routes = initial_routes
    best_metadata = {
        "feasibility": "OK",
        "vehicles": len(best_routes),
        "distance": sum(distance(instance.node_map[a], instance.node_map[b]) for route in best_routes for a, b in zip(route, route[1:]))
    }
    
    # Implement a search loop with time limit
    start_time = time.time()
    while time.time() - start_time < time_limit_s:
        candidate_routes = local_search(best_routes)
        if is_feasible(candidate_routes):
            candidate_distance = sum(distance(instance.node_map[a], instance.node_map[b]) for route in candidate_routes for a, b in zip(route, route[1:]))
            candidate_metadata = {
                "feasibility": "OK",
                "vehicles": len(candidate_routes),
                "distance": candidate_distance
            }
            if candidate_metadata["vehicles"] < best_metadata["vehicles"] or (candidate_metadata["vehicles"] == best_metadata["vehicles"] and candidate_distance < best_metadata["distance"]):
                best_routes = candidate_routes
                best_metadata = candidate_metadata
    
    return {"routes": best_routes, "metadata": best_metadata}