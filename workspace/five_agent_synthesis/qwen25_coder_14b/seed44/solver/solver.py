from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution
import random
import time

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id]]
    
    # List of unassigned customers
    unassigned_customers = list(instance.customer_ids)
    
    # Assign customers to routes
    while unassigned_customers:
        customer_id = random.choice(unassigned_customers)
        assigned = False
        
        for route in routes:
            # Check if adding the customer to the route is feasible
            if is_feasible_to_add(instance, route, customer_id):
                route.append(customer_id)
                unassigned_customers.remove(customer_id)
                assigned = True
                break
        
        # If no feasible route found, create a new route
        if not assigned:
            routes.append([instance.depot_id, customer_id])
            unassigned_customers.remove(customer_id)
    
    # Ensure each route ends at the depot
    for route in routes:
        if route[-1] != instance.depot_id:
            route.append(instance.depot_id)
    
    # Ensure feasibility and energy constraints
    routes = ensure_feasibility_and_energy(instance, routes)
    
    return {"routes": routes, "metadata": {}}

def is_feasible_to_add(instance, route, customer_id):
    # Check capacity
    if not has_capacity(instance, route, customer_id):
        return False
    
    # Check time window
    if not within_time_window(instance, route, customer_id):
        return False
    
    # Check energy
    if not has_energy(instance, route, customer_id):
        return False
    
    return True

def has_capacity(instance, route, customer_id):
    # Get the current load of the route
    current_load = sum(instance.node_map[node].load for node in route)
    # Get the load of the customer to be added
    customer_load = instance.node_map[customer_id].load
    # Check if adding the customer exceeds the vehicle capacity
    return current_load + customer_load <= instance.vehicle.capacity

def within_time_window(instance, route, customer_id):
    # Propagate the route to get the stop states
    stop_states = propagate_route(instance, route + [customer_id])
    # Get the arrival time of the customer
    arrival_time = stop_states[-1].arrival_time
    # Get the time window of the customer
    customer = instance.node_map[customer_id]
    return customer.start_time <= arrival_time <= customer.end_time

def has_energy(instance, route, customer_id):
    # Propagate the route to get the stop states
    stop_states = propagate_route(instance, route + [customer_id])
    # Get the battery arrival at the customer
    battery_arrival = stop_states[-1].battery_arrival
    # Check if the battery is sufficient to reach the next node (depot)
    return battery_arrival >= instance.vehicle.start_soc

def ensure_feasibility_and_energy(instance, routes):
    for route in routes:
        while not is_feasible(instance, route):
            route = insert_station(instance, route)
    return routes

def is_feasible(instance, route):
    stop_states = propagate_route(instance, route)
    for stop in stop_states:
        if stop.battery_arrival < 0:
            return False
    return True

def insert_station(instance, route):
    nearest_station = find_nearest_station(instance, route[-2])
    route.insert(-1, nearest_station)
    return route

def find_nearest_station(instance, node_id):
    node = instance.node_map[node_id]
    nearest_station = None
    min_distance = float('inf')
    for station in instance.stations:
        dist = distance(node, station)
        if dist < min_distance:
            min_distance = dist
            nearest_station = station.id
    return nearest_station