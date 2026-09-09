# charging.py

import random

def calculate_energy_required(start_node, end_node, vehicle):
    return energy_required(start_node, end_node, vehicle)

def full_recharge(vehicle, battery_on_arrival):
    return full_recharge(vehicle, battery_on_arrival)

class StopState:
    def __init__(self, battery_arrival, service_start, load, arrival_time):
        self.battery_arrival = battery_arrival
        self.service_start = service_start
        self.load = load
        self.arrival_time = arrival_time

def propagate_route(instance, node_ids: list[str]) -> list[StopState]:
    return propagate_route(instance, node_ids)

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot as the starting and ending point
    routes = [[instance.depot_id]]
    
    # Assign customers to routes
    for customer_id in instance.customer_ids:
        best_route_index = None
        min_energy_cost = float('inf')
        
        for i, route in enumerate(routes):
            if len(route) == 1:  # Only consider adding to the last route for simplicity
                start_node = instance.node_map[route[-1]]
                customer_node = instance.node_map[customer_id]
                
                energy_cost = calculate_energy_required(start_node, customer_node, instance.vehicle)
                if energy_cost < min_energy_cost:
                    best_route_index = i
                    min_energy_cost = energy_cost
        
        if best_route_index is not None:
            routes[best_route_index].append(customer_id)
        else:
            # If no route can accommodate the customer, create a new route
            routes.append([instance.depot_id, customer_id, instance.depot_id])
    
    return {"routes": routes, "metadata": {}}