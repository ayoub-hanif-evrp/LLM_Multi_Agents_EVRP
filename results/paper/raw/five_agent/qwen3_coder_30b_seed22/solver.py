import random
import time
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

import random
import time
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route


def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    start_time = time.time()
    
    # Initial greedy construction with route building
    routes = []
    unvisited_customers = set(instance.customer_ids)
    
    while unvisited_customers and (time.time() - start_time) < time_limit_s * 0.9:
        route = [instance.depot_id]
        current_node_id = instance.depot_id
        current_load = 0.0
        current_battery = instance.vehicle.start_soc
        current_time = 0.0
        
        # Build a single route until no more customers can be served
        while True:
            best_customer = None
            min_cost = float('inf')
            
            for customer_id in unvisited_customers:
                customer = instance.node_map[customer_id]
                
                # Check if we can reach this customer
                dist_to_customer = distance(instance.node_map[current_node_id], customer)
                energy_needed = energy_required(instance.node_map[current_node_id], customer, instance.vehicle)
                
                if current_battery >= energy_needed:
                    # Calculate travel time and service time
                    travel_t = travel_time(instance.node_map[current_node_id], customer, instance.vehicle)
                    service_t = customer.service_time
                    
                    # Compute arrival time at customer
                    estimated_arrival = current_time + travel_t
                    
                    # Check time window
                    if estimated_arrival <= customer.due_time:
                        cost = travel_t + service_t
                        
                        if cost < min_cost:
                            min_cost = cost
                            best_customer = customer_id
            
            if best_customer is None:
                # No more customers can be served, try to return to depot or find charging
                break
                
            route.append(best_customer)
            unvisited_customers.remove(best_customer)
            
            # Update load, battery, and time
            current_load += instance.node_map[best_customer].demand
            current_battery -= energy_needed
            travel_t = travel_time(instance.node_map[current_node_id], instance.node_map[best_customer], instance.vehicle)
            current_time += travel_t + instance.node_map[best_customer].service_time
            
            # Check if we need to charge
            if current_battery < 0.1:
                # Find nearest station to recharge
                best_station = None
                min_dist = float('inf')
                
                for station_id in instance.station_ids:
                    station = instance.node_map[station_id]
                    dist_to_station = distance(instance.node_map[current_node_id], station)
                    
                    if dist_to_station < min_dist:
                        min_dist = dist_to_station
                        best_station = station_id
                
                if best_station is not None:
                    route.append(best_station)
                    try:
                        states = propagate_route(instance, route)
                        current_battery = states[-1].battery_departure
                        current_time = states[-1].arrival_time
                    except Exception:
                        # If validation fails, remove the station and continue
                        route.pop()
                        break
            
            current_node_id = best_customer
        
        # Return to depot
        if len(route) > 1:
            depot_node = instance.node_map[instance.depot_id]
            customer_node = instance.node_map[current_node_id]
            travel_t = travel_time(customer_node, depot_node, instance.vehicle)
            energy_needed = energy_required(customer_node, depot_node, instance.vehicle)
            
            if current_battery >= energy_needed:
                route.append(instance.depot_id)
                routes.append(route)
            else:
                # Try to find a station to recharge before returning to depot
                best_station = None
                min_dist = float('inf')
                for station_id in instance.station_ids:
                    station = instance.node_map[station_id]
                    dist_to_station = distance(instance.node_map[current_node_id], station)
                    if dist_to_station < min_dist:
                        min_dist = dist_to_station
                        best_station = station_id
                
                if best_station is not None:
                    route.append(best_station)
                    try:
                        states = propagate_route(instance, route)
                        current_battery = states[-1].battery_departure
                        # Now check if we can return to depot
                        if current_battery >= energy_needed:
                            route.append(instance.depot_id)
                            routes.append(route)
                    except Exception:
                        pass  # Drop the route if it's still infeasible
    
    # If there are still unvisited customers, try to improve with local search
    if unvisited_customers:
        routes = improve_routes(routes, instance, time_limit_s - (time.time() - start_time))
    
    return {"routes": routes, "metadata": {}}

def improve_routes(routes, instance, remaining_time):
    # Simple 2-opt improvement for each route
    improved_routes = []
    
    for route in routes:
        if len(route) <= 3:
            improved_routes.append(route)
            continue
            
        best_route = route[:]
        improved = True
        
        while improved and (time.time() - time.time()) < remaining_time * 0.1:  # Prevent infinite loop
            improved = False
            for i in range(1, len(route) - 2):
                for j in range(i + 1, len(route)):
                    if j - i == 1: continue
                    
                    new_route = route[:]
                    new_route[i:j] = reversed(new_route[i:j])
                    
                    # Check feasibility
                    if is_feasible(new_route, instance):
                        # Calculate total distance
                        old_dist = calculate_total_distance(route, instance)
                        new_dist = calculate_total_distance(new_route, instance)
                        
                        if new_dist < old_dist:
                            route = new_route[:]
                            improved = True
                            break
                if improved:
                    break
                    
        improved_routes.append(route)
    
    return improved_routes

def is_feasible(route, instance):
    try:
        states = propagate_route(instance, route)
        
        for state in states:
            node = instance.node_map[state.node_id]
            
            # Check time window
            if state.arrival_time < node.ready_time or state.arrival_time > node.due_time:
                return False
                
            # Check capacity
            if state.load > instance.vehicle.capacity:
                return False
                
        return True
    except Exception:
        return False

def calculate_total_distance(route, instance):
    total = 0.0
    
    for i in range(len(route) - 1):
        a = instance.node_map[route[i]]
        b = instance.node_map[route[i+1]]
        total += distance(a, b)
        
    return total

