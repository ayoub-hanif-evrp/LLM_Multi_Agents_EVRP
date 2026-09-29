from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
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
        best_route_index = None
        best_route_cost = float('inf')
        
        for i, route in enumerate(routes):
            if len(route) == 1:
                cost = distance(instance.node_map[route[0]], customer) + distance(customer, instance.depot)
            else:
                cost = distance(instance.node_map[route[-1]], customer)
            
            if cost < best_route_cost:
                best_route_index = i
                best_route_cost = cost
        
        if best_route_index is not None:
            routes[best_route_index].append(customer_id)
        else:
            routes.append([depot_id, customer_id, depot_id])
    
    # Remove empty routes
    routes = [route for route in routes if len(route) > 1]
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {}
    }