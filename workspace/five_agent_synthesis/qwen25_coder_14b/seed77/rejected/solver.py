import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    def is_feasible(routes):
        candidate_solution = CandidateSolution(routes=routes)
        fault = first_fault(instance, candidate_solution)
        return fault["family"] == "OK"
    
    def initial_routes():
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
                current_battery = full_recharge(instance.vehicle, 0)
            
            if current_battery - energy_required(instance.node_map[current_route[-1]], customer, instance.vehicle) < 0:
                current_route.append(instance.depot_id)
                routes.append(current_route)
                current_route = [instance.depot_id]
                current_battery = full_recharge(instance.vehicle, 0)
            
            current_route.append(customer_id)
            current_load += customer.demand
            current_battery -= energy_required(instance.node_map[current_route[-2]], customer, instance.vehicle)
        
        if current_route:
            current_route.append(instance.depot_id)
            routes.append(current_route)
        
        return routes
    
    def charging_logic(instance, routes):
        for route in routes:
            current_battery = instance.vehicle.start_soc
            i = 0
            while i < len(route) - 1:
                current_node = instance.node_map[route[i]]
                next_node = instance.node_map[route[i + 1]]
                energy_needed = energy_required(current_node, next_node, instance.vehicle)
                
                if current_battery < energy_needed:
                    # Find the nearest charging station
                    nearest_station = min(
                        instance.stations,
                        key=lambda station: distance(station, current_node)
                    )
                    route.insert(i + 1, nearest_station.id)
                    current_battery = full_recharge(instance.vehicle, 0)
                else:
                    current_battery -= energy_needed
                    i += 1
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
                            new_routes = [route for route in routes if route != routes[i] and route != routes[j]] + [new_route_i, new_route_j]
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
    
    initial_routes = initial_routes()
    initial_routes = charging_logic(instance, initial_routes)
    if not is_feasible(initial_routes):
        return {"routes": [], "metadata": {"status": "initial routes not feasible"}}
    
    final_routes = local_search(initial_routes)
    final_routes = charging_logic(instance, final_routes)
    if not is_feasible(final_routes):
        return {"routes": [], "metadata": {"status": "final routes not feasible"}}
    
    return {"routes": final_routes, "metadata": {"status": "feasible"}}