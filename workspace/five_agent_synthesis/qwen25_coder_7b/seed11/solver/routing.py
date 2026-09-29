from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id]]
    
    # Assign customers to routes
    for customer_id in instance.customer_ids:
        min_cost = float('inf')
        best_route_index = -1
        
        for i, route in enumerate(routes):
            if len(route) == 1:
                cost = distance(instance.node_map[route[0]], instance.node_map[customer_id])
            else:
                cost = distance(instance.node_map[route[-1]], instance.node_map[customer_id])
            
            if cost < min_cost:
                min_cost = cost
                best_route_index = i
        
        routes[best_route_index].append(customer_id)
        routes[best_route_index].append(instance.depot_id)
    
    # Remove empty routes
    routes = [route for route in routes if len(route) > 1]
    
    # Insert stations to ensure full recharge
    for i, route in enumerate(routes):
        vehicle = instance.vehicle
        energy_required_route = calculate_energy_required(route, vehicle)
        if energy_required_route > vehicle.battery_capacity:
            while energy_required_route > vehicle.battery_capacity:
                nearest_station = find_nearest_station(route, vehicle)
                route = insert_station(route, nearest_station, vehicle)
                energy_required_route = calculate_energy_required(route, vehicle)
    
    return {"routes": routes, "metadata": {}}

def calculate_energy_required(route, vehicle):
    total_energy = 0
    for i in range(len(route) - 1):
        a = route[i]
        b = route[i + 1]
        total_energy += energy_required(instance.node_map[a], instance.node_map[b], vehicle)
    return total_energy

def find_nearest_station(route, vehicle):
    min_distance = float('inf')
    nearest_station = None
    for station_id in instance.station_ids:
        if station_id not in route:
            dist = distance(instance.node_map[route[-1]], instance.node_map[station_id])
            if dist < min_distance:
                min_distance = dist
                nearest_station = station_id
    return nearest_station

def insert_station(route, station_id, vehicle):
    min_energy = float('inf')
    insert_index = -1
    for i in range(len(route) - 1):
        a = route[i]
        b = route[i + 1]
        energy = energy_required(instance.node_map[a], instance.node_map[b], vehicle)
        if energy + energy_required(instance.node_map[b], instance.node_map[station_id], vehicle) + energy_required(instance.node_map[station_id], instance.node_map[a], vehicle) < min_energy:
            min_energy = energy + energy_required(instance.node_map[b], instance.node_map[station_id], vehicle) + energy_required(instance.node_map[station_id], instance.node_map[a], vehicle)
            insert_index = i + 1
    route.insert(insert_index, station_id)
    return route