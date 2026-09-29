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
        
        for customer_id in instance.customer_ids:
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
    
    def manage_battery(routes, instance):
        new_routes = []
        for route in routes:
            new_route = []
            current_battery = instance.vehicle.start_soc
            for node_id in route:
                node = instance.node_map[node_id]
                if node_id != instance.depot_id:
                    energy_needed = energy_required(instance.node_map[new_route[-1]], node, instance.vehicle)
                    if current_battery - energy_needed < 0:
                        # Find the nearest station to recharge
                        nearest_station = min(instance.stations, key=lambda s: distance(instance.node_map[s.id], node))
                        new_route.append(nearest_station.id)
                        current_battery = full_recharge(instance.vehicle, current_battery)
                    current_battery -= energy_needed
                new_route.append(node_id)
            new_routes.append(new_route)
        return new_routes
    
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
        routes = initial_solution()
        routes = manage_battery(routes, instance)
        routes = local_search(routes)
        return routes
    
    start_time = time.time()
    best_routes = construct_solution()
    best_metadata = {
        "feasibility": is_feasible(best_routes),
        "vehicles": len(best_routes),
        "distance": sum(distance(instance.node_map[best_routes[i][j]], instance.node_map[best_routes[i][j+1]]) for i in range(len(best_routes)) for j in range(len(best_routes[i]) - 1))
    }
    
    while time.time() - start_time < time_limit_s:
        new_routes = construct_solution()
        new_metadata = {
            "feasibility": is_feasible(new_routes),
            "vehicles": len(new_routes),
            "distance": sum(distance(instance.node_map[new_routes[i][j]], instance.node_map[new_routes[i][j+1]]) for i in range(len(new_routes)) for j in range(len(new_routes[i]) - 1))
        }
        
        if (new_metadata["feasibility"] and not best_metadata["feasibility"]) or \
           (new_metadata["feasibility"] == best_metadata["feasibility"] and new_metadata["vehicles"] < best_metadata["vehicles"]) or \
           (new_metadata["feasibility"] == best_metadata["feasibility"] and new_metadata["vehicles"] == best_metadata["vehicles"] and new_metadata["distance"] < best_metadata["distance"]):
            best_routes = new_routes
            best_metadata = new_metadata
    
    return {"routes": best_routes, "metadata": best_metadata}