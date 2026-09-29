from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution
from evrptw_autolab.problem.evaluator import first_fault
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id]]
    
    # List of all customer IDs
    unvisited_customers = list(instance.customer_ids)
    
    # Assign each customer to a route
    for customer_id in unvisited_customers:
        # Find the best route to add the customer
        best_route_index = None
        best_route_cost = float('inf')
        
        for route_index, route in enumerate(routes):
            # Calculate the cost of adding the customer to this route
            cost = calculate_energy_cost(route + [customer_id], instance)
            
            if cost < best_route_cost:
                best_route_cost = cost
                best_route_index = route_index
        
        # Add the customer to the best route
        routes[best_route_index].insert(-1, customer_id)
    
    # Ensure each route starts and ends at the depot
    for route in routes:
        if route[0] != instance.depot_id:
            route.insert(0, instance.depot_id)
        if route[-1] != instance.depot_id:
            route.append(instance.depot_id)
    
    # Optimize routes
    optimized_routes = []
    for route in routes:
        optimized_routes.append(optimize_route(route, instance))
    
    # Check for feasibility
    packet = first_fault(instance, CandidateSolution(routes=optimized_routes))
    if packet["family"] != "OK":
        raise ValueError(f"Feasibility check failed: {packet}")
    
    return {"routes": optimized_routes, "metadata": {}}

def calculate_energy_cost(route, instance):
    total_energy = 0
    current_node = instance.depot
    for node_id in route:
        next_node = instance.node_map[node_id]
        total_energy += energy_required(current_node, next_node, instance.vehicle)
        current_node = next_node
    return total_energy

def is_feasible_route(route, instance):
    stop_states = propagate_route(instance, route)
    for stop in stop_states:
        if stop.battery_arrival < 0:
            return False
    return True

def insert_station(route, instance):
    max_energy = instance.vehicle.battery_capacity
    current_energy = 0
    for i, node_id in enumerate(route):
        next_node = instance.node_map[node_id]
        current_energy += energy_required(instance.node_map[route[i-1]], next_node, instance.vehicle)
        if current_energy > max_energy:
            # Insert station before node_id
            route.insert(i, instance.station_ids[0])
            return route
    return route

def optimize_route(route, instance):
    route = insert_station(route, instance)
    return route