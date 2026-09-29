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
        vehicle = instance.vehicle
        current_route = [instance.depot_id]
        current_load = 0
        current_battery = vehicle.start_soc
        
        for customer_id in instance.customer_ids:
            customer = instance.node_map[customer_id]
            if current_load + customer.demand > vehicle.capacity:
                current_route.append(instance.depot_id)
                routes.append(current_route)
                current_route = [instance.depot_id]
                current_load = 0
                current_battery = vehicle.start_soc
            
            if current_battery < energy_required(customer, instance.node_map[instance.depot_id], vehicle):
                charge_decision = full_recharge(vehicle, current_battery)
                current_battery = charge_decision.battery_departure
                current_route.append(instance.depot_id)
            
            current_route.append(customer_id)
            current_load += customer.demand
            current_battery -= energy_required(customer, instance.node_map[instance.depot_id], vehicle)
        
        if current_route:
            current_route.append(instance.depot_id)
            routes.append(current_route)
        
        return routes
    
    def local_search(routes):
        # Placeholder for local search logic
        return routes
    
    def construct_solution():
        routes = initial_solution()
        routes = local_search(routes)
        return routes
    
    routes = construct_solution()
    
    if not is_feasible(routes):
        raise ValueError("Initial solution is not feasible")
    
    return {"routes": routes, "metadata": {}}