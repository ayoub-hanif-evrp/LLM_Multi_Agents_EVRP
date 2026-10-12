from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    station_ids = instance.station_ids
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle
    
    # Initialize routes with the depot
    routes = [[depot_id] for _ in range(len(customers))]
    
    # Function to calculate the total distance of a route
    def total_distance(route):
        return sum(distance(instance.node_map[route[i]], instance.node_map[route[i+1]]) for i in range(len(route)-1))
    
    # Function to calculate the total energy consumption of a route
    def total_energy_consumption(route):
        return sum(energy_required(instance.node_map[route[i]], instance.node_map[route[i+1]], vehicle) for i in range(len(route)-1))
    
    # Function to calculate the total battery deficit of a route
    def total_battery_deficit(route):
        states = propagate_route(instance, route)
        return sum(state.battery_departure - state.battery_arrival for state in states)
    
    # Function to insert a customer into a route
    def insert_customer(route, customer_id):
        best_insertion = None
        best_cost = float('inf')
        for i in range(len(route)):
            new_route = route[:i] + [customer_id] + route[i:]
            new_cost = total_distance(new_route) + total_energy_consumption(new_route) + total_battery_deficit(new_route)
            if new_cost < best_cost:
                best_cost = new_cost
                best_insertion = i
        if best_insertion is not None:
            route.insert(best_insertion, customer_id)
    
    # Insert customers into routes
    for customer_id in customer_ids:
        best_route = None
        best_cost = float('inf')
        for route in routes:
            insert_customer(route, customer_id)
            cost = total_distance(route) + total_energy_consumption(route) + total_battery_deficit(route)
            if cost < best_cost:
                best_cost = cost
                best_route = route
        if best_route is not None:
            best_route.append(depot_id)
            routes.remove(best_route)
            routes.append(best_route)
    
    # Convert routes to the required format
    result_routes = [[depot_id] + route[1:-1] + [depot_id] for route in routes]
    
    return {
        "routes": result_routes,
        "metadata": {
            "total_distance": sum(total_distance(route) for route in result_routes),
            "total_energy_consumption": sum(total_energy_consumption(route) for route in result_routes),
            "total_battery_deficit": sum(total_battery_deficit(route) for route in result_routes)
        }
    }