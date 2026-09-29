import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes
    routes = [[] for _ in range(instance.vehicle.capacity)]
    
    # Function to calculate the total distance of a route
    def total_distance(route):
        return sum(distance(instance.node_map[route[i]], instance.node_map[route[i+1]]) for i in range(len(route)-1))
    
    # Function to calculate the total energy consumption of a route
    def total_energy_consumption(route):
        return sum(energy_required(instance.node_map[route[i]], instance.node_map[route[i+1]], instance.vehicle) for i in range(len(route)-1))
    
    # Function to evaluate a route
    def evaluate_route(route):
        return total_distance(route), total_energy_consumption(route)
    
    # Function to insert a customer into a route
    def insert_customer(route, customer_id):
        best_insertion_index = -1
        best_insertion_cost = float('inf')
        for i in range(len(route)):
            new_route = route[:i] + [customer_id] + route[i:]
            cost = evaluate_route(new_route)
            if cost < best_insertion_cost:
                best_insertion_cost = cost
                best_insertion_index = i
        if best_insertion_index != -1:
            route.insert(best_insertion_index, customer_id)
    
    # Main optimization loop
    for customer_id in instance.customer_ids:
        best_route = None
        best_cost = float('inf')
        for route in routes:
            insert_customer(route, customer_id)
            cost = evaluate_route(route)
            if cost < best_cost:
                best_cost = cost
                best_route = route
        if best_route:
            best_route.append(customer_id)
            best_route.insert(0, instance.depot_id)
            best_route.append(instance.depot_id)
    
    # Return the solution
    return {"routes": routes, "metadata": {}}