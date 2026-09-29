import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id] for _ in range(int(instance.vehicle.capacity))]
    
    # Assign customers to routes
    for customer_id in instance.customer_ids:
        route = min(routes, key=lambda r: distance(instance.node_map[r[-1]], instance.node_map[customer_id]))
        route.append(customer_id)
        route.append(instance.depot_id)
    
    # Ensure all customers are visited
    visited_customers = set()
    for route in routes:
        for node_id in route:
            if node_id in instance.customer_ids:
                visited_customers.add(node_id)
    
    if len(visited_customers) != instance.n_customers:
        # If not all customers are visited, return an empty solution
        return {"routes": [], "metadata": {}}
    
    # Insert charges to ensure feasibility
    for i in range(len(routes)):
        routes[i] = insert_charges(instance, routes[i])
    
    # Check feasibility
    candidate_solution = CandidateSolution(routes=routes)
    fault = first_fault(instance, candidate_solution)
    
    if fault["family"] != "OK":
        # If there's a fault, try to fix it by recharging at stations
        for route in routes:
            for i in range(1, len(route) - 1):
                if fault["node_id"] == route[i]:
                    # Insert a recharge at the nearest station
                    nearest_station_id = find_nearest_station(instance, route[i])
                    route.insert(i + 1, nearest_station_id)
                    break
    
    # Final check
    candidate_solution = CandidateSolution(routes=routes)
    fault = first_fault(instance, candidate_solution)
    
    if fault["family"] != "OK":
        # If still not feasible, return an empty solution
        return {"routes": [], "metadata": {}}
    
    return {"routes": routes, "metadata": {}}

def full_recharge(vehicle, battery_on_arrival):
    energy_charged = vehicle.battery_capacity - battery_on_arrival
    duration = energy_charged / vehicle.inverse_refuel_rate
    battery_departure = vehicle.battery_capacity
    return ChargeDecision(energy_charged=energy_charged, duration=duration, battery_departure=battery_departure)

def is_feasible_route(instance, route):
    stop_states = propagate_route(instance, route)
    for stop_state in stop_states:
        if stop_state.battery_arrival < 0:
            return False
    return True

def find_nearest_station(instance, node_id):
    node = instance.node_map[node_id]
    nearest_station = min(instance.stations, key=lambda s: distance(node, s))
    return nearest_station.id

def insert_charges(instance, route):
    stop_states = propagate_route(instance, route)
    for i in range(1, len(route) - 1):
        if stop_states[i].battery_arrival < 0:
            nearest_station_id = find_nearest_station(instance, route[i])
            route.insert(i + 1, nearest_station_id)
            stop_states = propagate_route(instance, route)
    return route