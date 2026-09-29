import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution

def charging_logic(instance, routes):
    for route in routes:
        current_battery = instance.vehicle.start_soc
        for i in range(len(route) - 1):
            from_node = instance.node_map[route[i]]
            to_node = instance.node_map[route[i + 1]]
            energy_needed = energy_required(from_node, to_node, instance.vehicle)
            if current_battery < energy_needed:
                # Find the nearest station to recharge
                nearest_station = min(
                    instance.stations,
                    key=lambda station: distance(station, from_node)
                )
                # Insert the station into the route
                route.insert(i + 1, nearest_station.id)
                # Recharge the battery
                current_battery = full_recharge(instance.vehicle, current_battery)
            else:
                current_battery -= energy_needed
        # Ensure the route ends at the depot
        if route[-1] != instance.depot_id:
            route.append(instance.depot_id)
            current_battery = full_recharge(instance.vehicle, current_battery)

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
        charging_logic(instance, routes)
        routes = local_search(routes)
        return routes
    
    routes = construct_solution()
    metadata = {
        "feasibility": is_feasible(routes),
        "vehicles": len(routes),
        "distance": sum(distance(instance.node_map[routes[i][j]], instance.node_map[routes[i][j+1]]) for i in range(len(routes)) for j in range(len(routes[i]) - 1))
    }
    
    return {"routes": routes, "metadata": metadata}