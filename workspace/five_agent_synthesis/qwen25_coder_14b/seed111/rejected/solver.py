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
    
    def construct_initial_routes():
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
                current_battery = full_recharge(instance.vehicle, 0)
                current_time = 0
            
            travel = travel_time(instance.node_map[current_route[-1]], customer, instance.vehicle)
            if current_time + travel > customer.latest:
                routes.append(current_route + [instance.depot_id])
                current_route = [instance.depot_id]
                current_battery = full_recharge(instance.vehicle, 0)
                current_time = 0
            
            current_route.append(customer_id)
            current_load += customer.demand
            current_battery -= energy_required(instance.node_map[current_route[-2]], customer, instance.vehicle)
            current_time += travel + customer.service_duration
        
        if current_route:
            routes.append(current_route + [instance.depot_id])
        
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
                            new_route_i = routes[i][:k] + routes[j][l:k+1] + routes[i][k+1:]
                            new_route_j = routes[j][:l] + routes[i][k:l+1] + routes[j][l+1:]
                            new_routes = [new_route_i, new_route_j]
                            if is_feasible(new_routes):
                                routes[i] = new_route_i
                                routes[j] = new_route_j
                                improved = True
                                break
                        if improved:
                            break
                    if improved:
                        break
                if improved:
                    break
        return routes
    
    initial_routes = construct_initial_routes()
    if not is_feasible(initial_routes):
        return {"routes": [], "metadata": {"feasibility": "infeasible"}}
    
    final_routes = local_search(initial_routes)
    
    return {"routes": final_routes, "metadata": {"feasibility": "feasible"}}