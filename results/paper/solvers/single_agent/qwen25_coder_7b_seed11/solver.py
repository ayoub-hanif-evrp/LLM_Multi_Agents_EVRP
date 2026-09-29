from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle
    
    # Initialize routes
    routes = [[depot_id]]
    
    # Add customers to routes
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        min_cost = float('inf')
        best_route_index = -1
        
        for i, route in enumerate(routes):
            if len(route) == 1:
                cost = distance(instance.node_map[route[-1]], customer)
            else:
                cost = distance(instance.node_map[route[-1]], customer) + distance(customer, instance.node_map[route[0]])
            
            if cost < min_cost:
                min_cost = cost
                best_route_index = i
        
        if best_route_index == -1:
            routes.append([depot_id, customer_id, depot_id])
        else:
            routes[best_route_index].append(customer_id)
    
    # Add depot to the end of each route
    for route in routes:
        route.append(depot_id)
    
    # Check feasibility
    packet = first_fault(instance, CandidateSolution(routes=routes))
    if packet["family"] != "OK":
        print(f"First fault detected: {packet}")
    
    return {"routes": routes, "metadata": {}}