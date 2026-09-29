from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution
import random
import time

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id]]
    
    # List of unvisited customers
    unvisited_customers = list(instance.customer_ids)
    
    # Assign each customer to a route
    for customer_id in unvisited_customers:
        # Find the route with the least distance to the customer
        min_distance = float('inf')
        best_route_index = 0
        
        for i, route in enumerate(routes):
            # Calculate distance from the last node in the route to the customer
            last_node_id = route[-1]
            dist = distance(instance.node_map[last_node_id], instance.node_map[customer_id])
            
            if dist < min_distance:
                min_distance = dist
                best_route_index = i
        
        # Add the customer to the best route
        routes[best_route_index].append(customer_id)
    
    # Close each route by returning to the depot
    for route in routes:
        route.append(instance.depot_id)
    
    # Ensure all customers are visited exactly once
    all_customers_visited = set()
    for route in routes:
        all_customers_visited.update(route[1:-1])  # Exclude depot from count
    
    if len(all_customers_visited) != instance.n_customers:
        raise ValueError("Not all customers are visited exactly once.")
    
    # Check feasibility
    for route in routes:
        stop_states = propagate_route(instance, route)
        
        for i, stop_state in enumerate(stop_states):
            if stop_state.load > instance.vehicle.capacity:
                raise ValueError(f"Route {route} exceeds capacity at stop {i}.")
            if stop_state.battery_arrival < 0:
                raise ValueError(f"Route {route} has negative battery at stop {i}.")
    
    # Check for first fault
    fault_packet = first_fault(instance, CandidateSolution(routes=routes))
    if fault_packet["family"] != "OK":
        if fault_packet["family"] == "BATTERY":
            # Handle battery feasibility issue
            routes = ensure_battery_feasibility(instance, routes, instance.vehicle)
    
    return {
        "routes": routes,
        "metadata": {}
    }

def ensure_battery_feasibility(instance, routes, vehicle):
    for route in routes:
        stop_states = propagate_route(instance, route)
        for i, stop in enumerate(stop_states):
            if stop.battery_arrival < 0:
                route = insert_station(instance, route, route[i-1], vehicle)
                stop_states = propagate_route(instance, route)
    return routes

def insert_station(instance, route, node_id, vehicle):
    nearest_station = find_nearest_station(instance, node_id, vehicle)
    route.insert(route.index(node_id) + 1, nearest_station)
    return route

def find_nearest_station(instance, node_id, vehicle):
    nearest_station = None
    min_distance = float('inf')
    for station in instance.stations:
        d = distance(instance.node_map[node_id], station)
        if d < min_distance:
            min_distance = d
            nearest_station = station.id
    return nearest_station