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
    
    depot = instance.depot
    start_soc = vehicle.start_soc
    battery_capacity = vehicle.battery_capacity
    consumption_rate = vehicle.consumption_rate
    
    routes = []
    remaining_customers = set(customer_ids)
    
    while remaining_customers:
        route = [depot_id]
        current_node = depot
        current_load = 0
        current_battery = start_soc * battery_capacity
        
        while remaining_customers:
            next_customer = min(remaining_customers, key=lambda c: distance(current_node, instance.node_map[c]))
            if current_battery < energy_required(current_node, instance.node_map[next_customer], vehicle):
                break
            
            route.append(next_customer)
            remaining_customers.remove(next_customer)
            current_node = instance.node_map[next_customer]
            current_load += next_customer.demand
            current_battery -= energy_required(current_node, instance.node_map[next_customer], vehicle)
        
        if len(route) > 1:
            route.append(depot_id)
            routes.append(route)
    
    metadata = {
        "num_vehicles": len(routes),
        "total_distance": sum(distance(instance.node_map[a], instance.node_map[b]) for route in routes for a, b in zip(route, route[1:]))
    }
    
    return {"routes": routes, "metadata": metadata}