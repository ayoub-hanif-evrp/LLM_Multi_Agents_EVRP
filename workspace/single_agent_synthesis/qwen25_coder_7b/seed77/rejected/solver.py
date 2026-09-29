from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    vehicle = instance.vehicle
    
    # Initialize routes with the depot
    routes = [[depot_id] for _ in range(len(customers) + 1)]
    
    # Function to calculate the energy required for a route
    def energy_needed(route):
        total_energy = 0
        for i in range(len(route) - 1):
            a = instance.node_map[route[i]]
            b = instance.node_map[route[i + 1]]
            total_energy += energy_required(a, b, vehicle)
        return total_energy
    
    # Function to calculate the total distance of a route
    def total_distance(route):
        total_dist = 0
        for i in range(len(route) - 1):
            a = instance.node_map[route[i]]
            b = instance.node_map[route[i + 1]]
            total_dist += distance(a, b)
        return total_dist
    
    # Function to calculate the total energy consumption of all routes
    def total_energy_consumption(routes):
        total_energy = 0
        for route in routes:
            total_energy += energy_needed(route)
        return total_energy
    
    # Function to calculate the total distance of all routes
    def total_distance_of_routes(routes):
        total_dist = 0
        for route in routes:
            total_dist += total_distance(route)
        return total_dist
    
    # Function to check if a route is feasible
    def is_route_feasible(route):
        state = propagate_route(instance, route)
        for state in state:
            if state.battery_arrival < 0:
                return False
            if state.service_start > instance.node_map[route[state.route_index]].due_time:
                return False
        return True
    
    # Function to insert a customer into a route
    def insert_customer(route, customer_id):
        best_insertion = None
        best_energy_increase = float('inf')
        for i in range(len(route)):
            new_route = route[:i] + [customer_id] + route[i:]
            if is_route_feasible(new_route):
                energy_increase = energy_needed(new_route) - energy_needed(route)
                if energy_increase < best_energy_increase:
                    best_energy_increase = energy_increase
                    best_insertion = i
        if best_insertion is not None:
            route.insert(best_insertion, customer_id)
            return True
        return False
    
    # Main loop to assign customers to routes
    for customer_id in customer_ids:
        inserted = False
        for route in routes:
            if insert_customer(route, customer_id):
                inserted = True
                break
        if not inserted:
            routes.append([depot_id, customer_id, depot_id])
    
    # Remove empty routes
    routes = [route for route in routes if len(route) > 1]
    
    # Check feasibility of the solution
    packet = first_fault(instance, CandidateSolution(routes=routes))
    if packet["family"] != "OK":
        print(f"First fault: {packet}")
        return {"routes": routes, "metadata": {"feasible": False}}
    
    # Calculate total energy consumption and distance
    total_energy = total_energy_consumption(routes)
    total_dist = total_distance_of_routes(routes)
    
    return {"routes": routes, "metadata": {"feasible": True, "total_energy": total_energy, "total_distance": total_dist}}