import random
from typing import List, Dict
from evrptw_autolab.problem.types import EVRPTWInstance, Node, VehicleSpec
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> Dict[str, List[List[str]]]:
    random.seed(seed)
    
    # Initialize variables
    depot_id = instance.depot_id
    customer_ids = list(instance.customer_ids)
    station_ids = list(instance.station_ids)
    customers = list(instance.customers)
    stations = list(instance.stations)
    vehicle = instance.vehicle
    
    # Helper function to calculate the total distance of a route
    def total_distance(route: List[str]) -> float:
        total = 0
        for i in range(len(route) - 1):
            total += distance(instance.node_map[route[i]], instance.node_map[route[i + 1]])
        return total
    
    # Helper function to calculate the total energy consumption of a route
    def total_energy_consumption(route: List[str]) -> float:
        total = 0
        for i in range(len(route) - 1):
            total += energy_required(instance.node_map[route[i]], instance.node_map[route[i + 1]], vehicle)
        return total
    
    # Helper function to calculate the total energy required for a route
    def total_energy_required(route: List[str]) -> float:
        total = 0
        for i in range(len(route) - 1):
            total += energy_required(instance.node_map[route[i]], instance.node_map[route[i + 1]], vehicle)
        return total
    
    # Helper function to calculate the total energy charged at stations
    def total_energy_charged(route: List[str]) -> float:
        total = 0
        for node in route:
            if node in station_ids:
                stop_states = propagate_route(instance, route)
                for stop_state in stop_states:
                    if stop_state.node_id == node:
                        total += stop_state.energy_charged
        return total
    
    # Helper function to calculate the total number of vehicles used
    def total_vehicles_used(routes: List[List[str]]) -> int:
        return len(routes)
    
    # Helper function to calculate the total Euclidean distance
    def total_euclidean_distance(routes: List[List[str]]) -> float:
        total = 0
        for route in routes:
            total += total_distance(route)
        return total
    
    # Main algorithm
    routes = []
    remaining_customers = customer_ids.copy()
    remaining_stations = station_ids.copy()
    
    while remaining_customers:
        current_route = [depot_id]
        current_load = 0
        current_battery = vehicle.start_soc
        
        while remaining_customers and current_battery >= 0:
            # Select the next customer to visit
            next_customer = random.choice(remaining_customers)
            next_node = instance.node_map[next_customer]
            next_energy_required = energy_required(instance.node_map[current_route[-1]], next_node, vehicle)
            
            if current_battery >= next_energy_required:
                current_route.append(next_customer)
                remaining_customers.remove(next_customer)
                current_load += next_node.demand
                current_battery -= next_energy_required
            else:
                break
        
        # If there are remaining customers, find a charging station
        if remaining_customers:
            next_station = random.choice(remaining_stations)
            next_node = instance.node_map[next_station]
            next_energy_required = energy_required(instance.node_map[current_route[-1]], next_node, vehicle)
            next_full_recharge = full_recharge(vehicle, current_battery)
            
            if next_full_recharge.battery_departure >= next_energy_required:
                current_route.append(next_station)
                remaining_stations.remove(next_station)
                current_battery = next_full_recharge.battery_departure
            else:
                break
        
        # Add the current route to the list of routes
        current_route.append(depot_id)
        routes.append(current_route)
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {
            "total_distance": total_distance(routes),
            "total_energy_consumption": total_energy_consumption(routes),
            "total_energy_required": total_energy_required(routes),
            "total_energy_charged": total_energy_charged(routes),
            "total_vehicles_used": total_vehicles_used(routes),
            "total_euclidean_distance": total_euclidean_distance(routes)
        }
    }