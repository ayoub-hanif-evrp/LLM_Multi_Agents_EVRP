from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes
    routes = [[] for _ in range(instance.vehicle.capacity)]
    
    # Assign customers to routes
    for customer_id in instance.customer_ids:
        customer = instance.node_map[customer_id]
        best_route_index = None
        best_route_distance = float('inf')
        
        for i, route in enumerate(routes):
            if len(route) == 0:
                # Empty route, assign directly
                route.append(instance.depot_id)
                route.append(customer_id)
                route.append(instance.depot_id)
                break
            else:
                # Calculate the distance if this customer is added to the route
                last_node_id = route[-1]
                last_node = instance.node_map[last_node_id]
                new_distance = distance(last_node, customer) + distance(customer, instance.depot)
                if new_distance < best_route_distance:
                    best_route_index = i
                    best_route_distance = new_distance
        
        if best_route_index is not None:
            routes[best_route_index].append(customer_id)
    
    # Remove empty routes
    routes = [route for route in routes if len(route) > 0]
    
    # Check feasibility
    packet = first_fault(instance, CandidateSolution(routes=routes))
    if packet["family"] != "OK":
        # Fix the first fault
        if packet["family"] == "TIME_WINDOW":
            # Adjust the route to respect time windows
            for route in routes:
                route = propagate_route(instance, route)
                for i in range(1, len(route) - 1):
                    node = instance.node_map[route[i]]
                    if not instance.node_map[route[i - 1]].time_window.contains(node.arrival_time):
                        route = adjust_route_to_time_window(instance, route, i)
                        break
        elif packet["family"] == "CAPACITY":
            # Adjust the route to respect capacity
            for route in routes:
                route = propagate_route(instance, route)
                for i in range(1, len(route) - 1):
                    node = instance.node_map[route[i]]
                    if node.load > instance.vehicle.capacity:
                        route = adjust_route_to_capacity(instance, route, i)
                        break
        elif packet["family"] == "BATTERY":
            # Adjust the route to respect battery
            for route in routes:
                route = propagate_route(instance, route)
                for i in range(1, len(route) - 1):
                    node = instance.node_map[route[i]]
                    if node.battery_arrival < instance.vehicle.battery_capacity:
                        insert_charging_stations(instance, route)
    
    return {
        "routes": routes,
        "metadata": {}
    }

def adjust_route_to_time_window(instance, route, i):
    # Adjust the route to respect the time window
    # This is a placeholder function, you need to implement the logic to adjust the route
    return route

def adjust_route_to_capacity(instance, route, i):
    # Adjust the route to respect the capacity constraint
    # This is a placeholder function, you need to implement the logic to adjust the route
    return route

def insert_charging_stations(instance, route):
    vehicle = instance.vehicle
    for i in range(1, len(route) - 1):
        current_node = instance.node_map[route[i]]
        previous_node = instance.node_map[route[i - 1]]
        next_node = instance.node_map[route[i + 1]]
        
        current_energy_required = energy_required(previous_node, current_node, vehicle)
        next_energy_required = energy_required(current_node, next_node, vehicle)
        
        if current_node.battery_arrival + current_energy_required / vehicle.inverse_refuel_rate < vehicle.battery_capacity:
            for station_id in instance.station_ids:
                station = instance.node_map[station_id]
                if station_id not in route:
                    distance_to_station = distance(current_node, station)
                    energy_to_station = energy_required(current_node, station, vehicle)
                    energy_to_depot = energy_required(station, next_node, vehicle)
                    total_energy_required = energy_to_station + energy_to_depot
                    battery_arrival_at_station = current_node.battery_arrival + energy_to_station / vehicle.inverse_refuel_rate
                    battery_arrival_at_depot = battery_arrival_at_station + energy_to_depot / vehicle.inverse_refuel_rate
                    
                    if battery_arrival_at_depot <= vehicle.battery_capacity:
                        route.insert(i + 1, station_id)
                        full_recharge(vehicle, current_node.battery_arrival)
                        current_node.battery_arrival = battery_arrival_at_station
                        break