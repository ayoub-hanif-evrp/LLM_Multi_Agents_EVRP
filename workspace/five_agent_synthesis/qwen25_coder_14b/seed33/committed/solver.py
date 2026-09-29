import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    def initial_routes(instance):
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
                charge_decision = full_recharge(instance.vehicle, current_battery)
                current_time += charge_decision.duration
                current_battery = charge_decision.battery_departure
            
            current_time += travel_time(instance.node_map[current_route[-1]], customer, instance.vehicle)
            current_battery -= energy_required(instance.node_map[current_route[-1]], customer, instance.vehicle)
            current_load += customer.demand
            
            current_route.append(customer_id)
        
        if current_route:
            routes.append(current_route + [instance.depot_id])
        
        return routes

    def is_feasible(routes):
        candidate_solution = CandidateSolution(routes=routes)
        fault = first_fault(instance, candidate_solution)
        return fault["family"] == "OK"

    def repair_routes(routes):
        # Simple repair heuristic: if a route is infeasible, try to split it
        for i, route in enumerate(routes):
            if not is_feasible([route]):
                # Try to split the route at each possible point
                for j in range(1, len(route) - 1):
                    new_routes = routes[:i] + [route[:j+1], route[j+1:]] + routes[i+1:]
                    if is_feasible(new_routes):
                        return new_routes
        return routes

    # Initial route generation
    routes = initial_routes(instance)
    
    # Repair infeasible routes
    routes = repair_routes(routes)
    
    # Ensure all routes start and end at the depot
    for i, route in enumerate(routes):
        if route[0] != instance.depot_id or route[-1] != instance.depot_id:
            routes[i] = [instance.depot_id] + route + [instance.depot_id]
    
    return {"routes": routes, "metadata": {}}