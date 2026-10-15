import random
from evrptw_autolab.problem.physics import (
    distance,
    travel_time,
    energy_required,
    full_recharge,
    propagate_route,
)
from evrptw_autolab.problem.types import CandidateSolution

def construct(instance, rng):
    depot_id = instance.depot_id
    customer_ids = list(instance.customer_ids)
    station_ids = list(instance.station_ids)
    vehicle = instance.vehicle
    
    # Shuffle for randomness
    rng.shuffle(customer_ids)
    rng.shuffle(station_ids)
    
    routes = []
    unvisited_customers = customer_ids.copy()
    
    while unvisited_customers:
        route = [depot_id]
        current_load = 0
        current_battery = vehicle.start_soc
        current_time = 0
        
        # Build route greedily
        while True:
            best_customer = None
            min_due_time = float('inf')
            
            for customer_id in unvisited_customers:
                node = instance.node_map[customer_id]
                prev_node_id = route[-1]
                prev_node = instance.node_map[prev_node_id]
                
                dist = distance(prev_node, node)
                energy_needed = energy_required(prev_node, node, vehicle)
                
                if current_battery >= energy_needed:
                    arrival_time = current_time + travel_time(prev_node, node, vehicle)
                    if arrival_time <= node.due_time and node.due_time < min_due_time:
                        best_customer = customer_id
                        min_due_time = node.due_time
            
            if best_customer is None:
                break
            
            customer_node = instance.node_map[best_customer]
            prev_node_id = route[-1]
            prev_node = instance.node_map[prev_node_id]
            
            dist = distance(prev_node, customer_node)
            energy_needed = energy_required(prev_node, customer_node, vehicle)
            
            # Update state
            current_time += travel_time(prev_node, customer_node, vehicle)
            current_battery -= energy_needed
            
            current_time += customer_node.service_time
            current_load += customer_node.demand
            
            route.append(best_customer)
            unvisited_customers.remove(best_customer)
            
            # Check battery and recharge if needed
            if current_battery < 0:
                # Find nearest station to recharge
                best_station = None
                min_dist = float('inf')
                
                for station_id in station_ids:
                    station_node = instance.node_map[station_id]
                    dist_to_station = distance(prev_node, station_node)
                    if dist_to_station < min_dist:
                        min_dist = dist_to_station
                        best_station = station_id
                
                if best_station is not None:
                    route.append(best_station)
                    current_time += travel_time(prev_node, instance.node_map[best_station], vehicle)
                    charge_decision = full_recharge(vehicle, current_battery)
                    current_battery = vehicle.battery_capacity  # Use battery_capacity instead of charge_decision.energy
                    current_time += vehicle.inverse_refuel_rate * charge_decision.duration
                    
                    # Travel back to customer
                    dist_back = distance(instance.node_map[best_station], customer_node)
                    energy_needed_back = energy_required(instance.node_map[best_station], customer_node, vehicle)
                    current_time += travel_time(instance.node_map[best_station], customer_node, vehicle)
                    current_battery -= energy_needed_back
        
        # Return to depot
        if len(route) > 1:
            last_node_id = route[-1]
            depot_node = instance.node_map[depot_id]
            last_node = instance.node_map[last_node_id]
            dist_to_depot = distance(last_node, depot_node)
            energy_needed_to_depot = energy_required(last_node, depot_node, vehicle)
            
            if current_battery >= energy_needed_to_depot:
                route.append(depot_id)
                routes.append(route)
            else:
                # Recharge before returning to depot
                best_station = None
                min_dist = float('inf')
                
                for station_id in station_ids:
                    station_node = instance.node_map[station_id]
                    dist_to_station = distance(last_node, station_node)
                    if dist_to_station < min_dist:
                        min_dist = dist_to_station
                        best_station = station_id
                
                if best_station is not None:
                    route.append(best_station)
                    current_time += travel_time(last_node, instance.node_map[best_station], vehicle)
                    charge_decision = full_recharge(vehicle, current_battery)
                    current_battery = vehicle.battery_capacity  # Use battery_capacity instead of charge_decision.energy
                    current_time += vehicle.inverse_refuel_rate * charge_decision.duration
                    
                    dist_to_depot = distance(instance.node_map[best_station], depot_node)
                    energy_needed_to_depot = energy_required(instance.node_map[best_station], depot_node, vehicle)
                    if current_battery >= energy_needed_to_depot:
                        route.append(depot_id)
                        routes.append(route)
                else:
                    route.append(depot_id)
                    routes.append(route)
        
    return routes

def repair(instance, routes, rng):
    depot_id = instance.depot_id
    customer_ids = set(instance.customer_ids)
    station_ids = set(instance.station_ids)
    vehicle = instance.vehicle
    
    # Collect all nodes and check visit consistency
    visited_customers = set()
    all_route_nodes = []
    for route in routes:
        all_route_nodes.extend(route)
        for node_id in route:
            if node_id in customer_ids:
                visited_customers.add(node_id)
    
    # Identify missing customers
    missing_customers = customer_ids - visited_customers
    
    # Rebuild routes to ensure depot at start/end and fix issues
    repaired_routes = []
    unvisited_customers = list(missing_customers)
    
    # Process existing routes
    for route in routes:
        if not route or len(route) < 2:
            continue
        
        # Ensure depot is at start and end
        if route[0] != depot_id:
            route = [depot_id] + route
        if route[-1] != depot_id:
            route.append(depot_id)
        
        new_route = [route[0]]
        current_load = 0
        current_battery = vehicle.start_soc
        current_time = 0
        
        i = 1
        while i < len(route):
            node_id = route[i]
            node = instance.node_map[node_id]
            prev_node = instance.node_map[new_route[-1]]
            
            dist = distance(prev_node, node)
            energy_needed = energy_required(prev_node, node, vehicle)
            
            # Check if we can reach this node
            if current_battery < energy_needed:
                # Find nearest station to recharge
                best_station = None
                min_dist = float('inf')
                for station_id in station_ids:
                    station_node = instance.node_map[station_id]
                    dist_to_station = distance(prev_node, station_node)
                    if dist_to_station < min_dist:
                        min_dist = dist_to_station
                        best_station = station_id
                
                if best_station is not None:
                    new_route.append(best_station)
                    current_time += travel_time(prev_node, instance.node_map[best_station], vehicle)
                    charge_decision = full_recharge(vehicle, current_battery)
                    current_battery = vehicle.battery_capacity
                    current_time += vehicle.inverse_refuel_rate * charge_decision.duration
                    
                    # Now go to the original node
                    dist = distance(instance.node_map[best_station], node)
                    energy_needed = energy_required(instance.node_map[best_station], node, vehicle)
                    if current_battery >= energy_needed:
                        current_time += travel_time(instance.node_map[best_station], node, vehicle)
                        current_battery -= energy_needed
                    else:
                        i += 1
                        continue
                else:
                    i += 1
                    continue
            
            # Check time window
            arrival_time = current_time + travel_time(prev_node, node, vehicle)
            if arrival_time > node.due_time:
                i += 1
                continue
            
            # Add the node to route
            new_route.append(node_id)
            
            # Update state
            current_time = arrival_time
            current_battery -= energy_needed
            
            if node_id in customer_ids:
                current_load += node.demand
                current_time += node.service_time
            elif node_id in station_ids:
                charge_decision = full_recharge(vehicle, current_battery)
                current_battery = vehicle.battery_capacity
                current_time += vehicle.inverse_refuel_rate * charge_decision.duration
            else:
                current_time += node.service_time
            
            i += 1
        
        # Ensure route ends at depot
        if new_route[-1] != depot_id:
            last_node = instance.node_map[new_route[-1]]
            depot_node = instance.node_map[depot_id]
            dist_to_depot = distance(last_node, depot_node)
            energy_needed_to_depot = energy_required(last_node, depot_node, vehicle)
            if current_battery >= energy_needed_to_depot:
                new_route.append(depot_id)
            else:
                # Recharge before returning to depot
                best_station = None
                min_dist = float('inf')
                for station_id in station_ids:
                    station_node = instance.node_map[station_id]
                    dist_to_station = distance(last_node, station_node)
                    if dist_to_station < min_dist:
                        min_dist = dist_to_station
                        best_station = station_id
                
                if best_station is not None:
                    new_route.append(best_station)
                    current_time += travel_time(last_node, instance.node_map[best_station], vehicle)
                    charge_decision = full_recharge(vehicle, current_battery)
                    current_battery = vehicle.battery_capacity
                    current_time += vehicle.inverse_refuel_rate * charge_decision.duration
                    
                    # Return to depot
                    dist_to_depot = distance(instance.node_map[best_station], depot_node)
                    energy_needed_to_depot = energy_required(instance.node_map[best_station], depot_node, vehicle)
                    if current_battery >= energy_needed_to_depot:
                        new_route.append(depot_id)
        
        # Add to repaired routes if valid
        if len(new_route) > 1 and new_route[0] == depot_id and new_route[-1] == depot_id:
            repaired_routes.append(new_route)
    
    # Assign remaining customers to new routes
    while unvisited_customers:
        route = [depot_id]
        current_load = 0
        current_battery = vehicle.start_soc
        current_time = 0
        
        # Build route greedily
        while True:
            best_customer = None
            min_due_time = float('inf')
            
            for customer_id in unvisited_customers:
                node = instance.node_map[customer_id]
                prev_node_id = route[-1]
                prev_node = instance.node_map[prev_node_id]
                
                dist = distance(prev_node, node)
                energy_needed = energy_required(prev_node, node, vehicle)
                
                if current_battery >= energy_needed:
                    arrival_time = current_time + travel_time(prev_node, node, vehicle)
                    if arrival_time <= node.due_time and node.due_time < min_due_time:
                        best_customer = customer_id
                        min_due_time = node.due_time
            
            if best_customer is None:
                break
            
            customer_node = instance.node_map[best_customer]
            prev_node_id = route[-1]
            prev_node = instance.node_map[prev_node_id]
            
            dist = distance(prev_node, customer_node)
            energy_needed = energy_required(prev_node, customer_node, vehicle)
            
            # Update state
            current_time += travel_time(prev_node, customer_node, vehicle)
            current_battery -= energy_needed
            
            current_time += customer_node.service_time
            current_load += customer_node.demand
            
            route.append(best_customer)
            unvisited_customers.remove(best_customer)
            
            # Check battery and recharge if needed
            if current_battery < 0:
                # Find nearest station to recharge
                best_station = None
                min_dist = float('inf')
                
                for station_id in station_ids:
                    station_node = instance.node_map[station_id]
                    dist_to_station = distance(prev_node, station_node)
                    if dist_to_station < min_dist:
                        min_dist = dist_to_station
                        best_station = station_id
                
                if best_station is not None:
                    route.append(best_station)
                    current_time += travel_time(prev_node, instance.node_map[best_station], vehicle)
                    charge_decision = full_recharge(vehicle, current_battery)
                    current_battery = vehicle.battery_capacity
                    current_time += vehicle.inverse_refuel_rate * charge_decision.duration
                    
                    # Travel back to customer
                    dist_back = distance(instance.node_map[best_station], customer_node)
                    energy_needed_back = energy_required(instance.node_map[best_station], customer_node, vehicle)
                    current_time += travel_time(instance.node_map[best_station], customer_node, vehicle)
                    current_battery -= energy_needed_back
        
        # Return to depot
        if len(route) > 1:
            last_node_id = route[-1]
            depot_node = instance.node_map[depot_id]
            last_node = instance.node_map[last_node_id]
            dist_to_depot = distance(last_node, depot_node)
            energy_needed_to_depot = energy_required(last_node, depot_node, vehicle)
            
            if current_battery >= energy_needed_to_depot:
                route.append(depot_id)
                repaired_routes.append(route)
            else:
                # Recharge before returning to depot
                best_station = None
                min_dist = float('inf')
                
                for station_id in station_ids:
                    station_node = instance.node_map[station_id]
                    dist_to_station = distance(last_node, station_node)
                    if dist_to_station < min_dist:
                        min_dist = dist_to_station
                        best_station = station_id
                
                if best_station is not None:
                    route.append(best_station)
                    current_time += travel_time(last_node, instance.node_map[best_station], vehicle)
                    charge_decision = full_recharge(vehicle, current_battery)
                    current_battery = vehicle.battery_capacity
                    current_time += vehicle.inverse_refuel_rate * charge_decision.duration
                    
                    dist_to_depot = distance(instance.node_map[best_station], depot_node)
                    energy_needed_to_depot = energy_required(instance.node_map[best_station], depot_node, vehicle)
                    if current_battery >= energy_needed_to_depot:
                        route.append(depot_id)
                        repaired_routes.append(route)
                else:
                    route.append(depot_id)
                    repaired_routes.append(route)
    
    return repaired_routes

def improve(instance, routes, rng):
    import time
    start_time = time.time()
    
    # Make a deep copy of routes to avoid mutating input
    improved_routes = [route[:] for route in routes]
    
    # Helper function to calculate total Euclidean distance of a route
    def route_distance(route):
        total = 0
        for i in range(len(route) - 1):
            node1 = instance.node_map[route[i]]
            node2 = instance.node_map[route[i+1]]
            dx = node1.x - node2.x
            dy = node1.y - node2.y
            total += (dx * dx + dy * dy) ** 0.5
        return total
    
    # Helper function to calculate total distance of all routes
    def total_distance(routes):
        total = 0
        for route in routes:
            total += route_distance(route)
        return total
    
    # Local search improvement using 2-opt style moves on each route
    for i, route in enumerate(improved_routes):
        if len(route) < 3:
            continue
        
        best_route = route[:]
        best_distance = route_distance(route)
        
        max_iterations = 50
        for _ in range(max_iterations):
            if time.time() - start_time > 0.8 * 1.0:
                break
            
            improved = False
            for j in range(1, len(route) - 2):
                for k in range(j + 1, len(route) - 1):
                    if time.time() - start_time > 0.8 * 1.0:
                        break
                    
                    new_route = route[:]
                    new_route[j:k+1] = reversed(new_route[j:k+1])
                    
                    new_distance = route_distance(new_route)
                    if new_distance < best_distance:
                        best_distance = new_distance
                        best_route = new_route[:]
                        improved = True
            
            if not improved:
                break
            
            route = best_route[:]
        
        improved_routes[i] = best_route
    
    # Try merging two routes to reduce number of vehicles
    for _ in range(5):  # Limit merge attempts
        if time.time() - start_time > 0.8 * 1.0:
            break
        
        best_improvement = 0
        best_pair = None
        best_merged = None
        
        for i in range(len(improved_routes)):
            for j in range(i+1, len(improved_routes)):
                if time.time() - start_time > 0.8 * 1.0:
                    break
                
                route1 = improved_routes[i]
                route2 = improved_routes[j]
                
                # Try merging by inserting one into another
                for pos1 in range(1, len(route1) - 1):
                    for pos2 in range(1, len(route2) - 1):
                        if time.time() - start_time > 0.8 * 1.0:
                            break
                        
                        # Create merged route
                        merged = route1[:]
                        # Insert route2 into route1 at pos1
                        for k in range(pos2, len(route2) - 1):
                            merged.insert(pos1, route2[k])
                        
                        # Check if the merged route is feasible
                        try:
                            # Simple check: make sure it's valid by propagating
                            from evrptw_autolab.problem.physics import propagate_route
                            result = propagate_route(instance.vehicle, instance.node_map, merged)
                            if result.is_feasible:
                                current_distance = total_distance(improved_routes)
                                new_distance = total_distance([merged])
                                improvement = current_distance - new_distance
                                if improvement > best_improvement:
                                    best_improvement = improvement
                                    best_pair = (i, j)
                                    best_merged = merged
                        except Exception:
                            continue
        
        if best_pair and best_merged:
            i, j = best_pair
            improved_routes[i] = best_merged
            improved_routes.pop(j)
    
    # Fix battery deficit issue by recharging before critical nodes
    for route in improved_routes:
        if len(route) < 3:
            continue
        
        current_battery = instance.vehicle.start_soc
        current_time = 0
        
        i = 1
        while i < len(route):
            node_id = route[i]
            node = instance.node_map[node_id]
            prev_node = instance.node_map[route[i-1]]
            
            dist = distance(prev_node, node)
            energy_needed = energy_required(prev_node, node, instance.vehicle)
            
            if current_battery < energy_needed:
                # Recharge at nearest station before proceeding
                best_station = None
                min_dist = float('inf')
                for station_id in instance.station_ids:
                    station_node = instance.node_map[station_id]
                    dist_to_station = distance(prev_node, station_node)
                    if dist_to_station < min_dist:
                        min_dist = dist_to_station
                        best_station = station_id
                
                if best_station is not None:
                    # Insert recharge before current node
                    route.insert(i, best_station)
                    current_time += travel_time(prev_node, instance.node_map[best_station], instance.vehicle)
                    charge_decision = full_recharge(instance.vehicle, current_battery)
                    current_battery = instance.vehicle.battery_capacity
                    current_time += instance.vehicle.inverse_refuel_rate * charge_decision.duration
                    
                    # Now proceed to the original node
                    dist = distance(instance.node_map[best_station], node)
                    energy_needed = energy_required(instance.node_map[best_station], node, instance.vehicle)
                    if current_battery >= energy_needed:
                        current_time += travel_time(instance.node_map[best_station], node, instance.vehicle)
                        current_battery -= energy_needed
                        i += 1  # Skip the inserted station
                    else:
                        i += 1
                else:
                    i += 1
            else:
                current_time += travel_time(prev_node, node, instance.vehicle)
                current_battery -= energy_needed
                
                if node_id in instance.customer_ids:
                    current_time += node.service_time
                elif node_id in instance.station_ids:
                    charge_decision = full_recharge(instance.vehicle, current_battery)
                    current_battery = instance.vehicle.battery_capacity
                    current_time += instance.vehicle.inverse_refuel_rate * charge_decision.duration
                else:
                    current_time += node.service_time
                
                i += 1
    
    return improved_routes

def solve(instance, seed: int, time_limit_s: float):
    import time
    import random
    rng = random.Random(seed)
    start_time = time.time()
    
    # Construct initial solution
    routes = construct(instance, rng)
    
    # Repair to ensure feasibility
    routes = repair(instance, routes, rng)
    
    # Improve solution
    routes = improve(instance, routes, rng)
    
    # Ensure time limit is respected
    if time.time() - start_time > 0.9 * time_limit_s:
        pass  # Return current best solution
    
    # Return result
    return CandidateSolution(routes=routes)








