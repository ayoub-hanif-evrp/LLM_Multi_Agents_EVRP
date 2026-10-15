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
    node_map = instance.node_map
    
    # Shuffle customers to add randomness
    rng.shuffle(customer_ids)
    
    routes = []
    current_route = [depot_id]
    current_load = 0
    current_battery = vehicle.start_soc
    current_time = 0
    
    def get_distance(a, b):
        return distance(node_map[a], node_map[b])
    
    def get_energy(a, b):
        return energy_required(node_map[a], node_map[b], vehicle)
    
    def can_visit_customer(customer_id):
        customer = node_map[customer_id]
        if current_load + customer.demand > vehicle.capacity:
            return False
        travel_time_to = travel_time(node_map[current_route[-1]], node_map[customer_id], vehicle)
        arrival_time = current_time + travel_time_to
        if arrival_time > customer.due_time:
            return False
        energy_needed = get_energy(current_route[-1], customer_id)
        if current_battery < energy_needed:
            return False
        return True
    
    def visit_customer(customer_id):
        nonlocal current_load, current_battery, current_time
        customer = node_map[customer_id]
        travel_time_to = travel_time(node_map[current_route[-1]], node_map[customer_id], vehicle)
        arrival_time = current_time + travel_time_to
        if arrival_time < customer.ready_time:
            wait_time = customer.ready_time - arrival_time
            current_time += wait_time
            arrival_time = customer.ready_time
        
        energy_used = get_energy(current_route[-1], customer_id)
        current_battery -= energy_used
        current_route.append(customer_id)
        current_load += customer.demand
        current_time = arrival_time + customer.service_time
        # Battery gains from service
        current_battery += customer.service_time * vehicle.consumption_rate * vehicle.velocity
    
    def visit_station(station_id):
        nonlocal current_battery, current_time
        travel_time_to = travel_time(node_map[current_route[-1]], node_map[station_id], vehicle)
        arrival_time = current_time + travel_time_to
        current_time = arrival_time
        current_battery -= get_energy(current_route[-1], station_id)
        
        charge_decision = full_recharge(vehicle.battery_capacity, current_battery)
        current_battery = charge_decision.new_soc
        
        current_route.append(station_id)
        current_time += vehicle.inverse_refuel_rate  # Charging time
    
    def finalize_route():
        nonlocal current_route, current_load, current_battery, current_time
        if len(current_route) > 1:
            travel_time_to = travel_time(node_map[current_route[-1]], node_map[depot_id], vehicle)
            current_time += travel_time_to
            current_battery -= get_energy(current_route[-1], depot_id)
            
            current_route.append(depot_id)
            routes.append(current_route)
        
        current_route = [depot_id]
        current_load = 0
        current_battery = vehicle.start_soc
        current_time = 0
    
    # Main assignment loop
    i = 0
    while i < len(customer_ids):
        customer_id = customer_ids[i]
        
        if can_visit_customer(customer_id):
            visit_customer(customer_id)
            i += 1
        else:
            # Try to recharge before continuing
            found_station = False
            for station_id in station_ids:
                energy_needed = get_energy(current_route[-1], station_id)
                if current_battery >= energy_needed:
                    visit_station(station_id)
                    found_station = True
                    break
            
            if not found_station:
                # Cannot proceed, finalize route and start new
                finalize_route()
                continue
    
    # Finalize last route
    finalize_route()
    
    return routes

def repair(instance, routes, rng):
    depot_id = instance.depot_id
    customer_ids = set(instance.customer_ids)
    station_ids = set(instance.station_ids)
    vehicle = instance.vehicle
    node_map = instance.node_map
    
    # Collect all nodes in routes
    visited_customers = set()
    all_route_nodes = []
    for route in routes:
        if not route:
            continue
        all_route_nodes.extend(route)
        for node in route:
            if node in customer_ids:
                visited_customers.add(node)
    
    # Missing customers
    missing_customers = customer_ids - visited_customers
    
    # Ensure depot at start and end of each route
    cleaned_routes = []
    for route in routes:
        if not route:
            continue
        if route[0] != depot_id:
            route = [depot_id] + route
        if route[-1] != depot_id:
            route = route + [depot_id]
        cleaned_routes.append(route)
    
    # Rebuild routes with proper constraints
    new_routes = []
    current_route = [depot_id]
    current_load = 0
    current_battery = vehicle.start_soc
    current_time = 0
    
    def get_distance(a, b):
        return distance(node_map[a], node_map[b])
    
    def get_energy(a, b):
        return energy_required(node_map[a], node_map[b], vehicle)
    
    def can_visit_customer(customer_id):
        customer = node_map[customer_id]
        if current_load + customer.demand > vehicle.capacity:
            return False
        travel_time_to = travel_time(node_map[current_route[-1]], node_map[customer_id], vehicle)
        arrival_time = current_time + travel_time_to
        if arrival_time > customer.due_time:
            return False
        energy_needed = get_energy(current_route[-1], customer_id)
        if current_battery < energy_needed:
            return False
        return True
    
    def visit_customer(customer_id):
        nonlocal current_load, current_battery, current_time
        customer = node_map[customer_id]
        travel_time_to = travel_time(node_map[current_route[-1]], node_map[customer_id], vehicle)
        arrival_time = current_time + travel_time_to
        if arrival_time < customer.ready_time:
            wait_time = customer.ready_time - arrival_time
            current_time += wait_time
            arrival_time = customer.ready_time
        
        energy_used = get_energy(current_route[-1], customer_id)
        current_battery -= energy_used
        current_route.append(customer_id)
        current_load += customer.demand
        current_time = arrival_time + customer.service_time
        # Battery gains from service
        current_battery += customer.service_time * vehicle.consumption_rate * vehicle.velocity
    
    def visit_station(station_id):
        nonlocal current_battery, current_time
        travel_time_to = travel_time(node_map[current_route[-1]], node_map[station_id], vehicle)
        arrival_time = current_time + travel_time_to
        current_time = arrival_time
        current_battery -= get_energy(current_route[-1], station_id)
        
        charge_decision = full_recharge(vehicle.battery_capacity, current_battery)
        current_battery = charge_decision.new_soc
        
        current_route.append(station_id)
        current_time += vehicle.inverse_refuel_rate  # Charging time
    
    def finalize_route():
        nonlocal current_route, current_load, current_battery, current_time
        if len(current_route) > 1:
            travel_time_to = travel_time(node_map[current_route[-1]], node_map[depot_id], vehicle)
            current_time += travel_time_to
            current_battery -= get_energy(current_route[-1], depot_id)
            
            current_route.append(depot_id)
            new_routes.append(current_route)
        
        current_route = [depot_id]
        current_load = 0
        current_battery = vehicle.start_soc
        current_time = 0
    
    # Process existing routes
    for route in cleaned_routes:
        if not route or len(route) < 2:
            continue
        
        i = 0
        while i < len(route):
            node_id = route[i]
            if node_id == depot_id:
                if i > 0 and i < len(route) - 1:
                    # Internal depot, skip
                    i += 1
                    continue
                else:
                    # Start or end of route
                    i += 1
                    continue
            elif node_id in customer_ids:
                if can_visit_customer(node_id):
                    visit_customer(node_id)
                    i += 1
                else:
                    # Try to recharge before visiting
                    found_station = False
                    for station_id in station_ids:
                        energy_needed = get_energy(current_route[-1], station_id)
                        if current_battery >= energy_needed:
                            visit_station(station_id)
                            # Retry customer
                            if can_visit_customer(node_id):
                                visit_customer(node_id)
                                found_station = True
                                break
                    
                    if not found_station:
                        # Cannot proceed with this route, finalize and start new
                        finalize_route()
                        continue
            else:
                # Node is a station
                if node_id in station_ids:
                    visit_station(node_id)
                i += 1
        
        # Finalize route if not empty
        if len(current_route) > 1:
            finalize_route()
    
    # Add missing customers
    for customer_id in missing_customers:
        inserted = False
        for i, route in enumerate(new_routes):
            temp_route = list(route)
            temp_load = current_load
            temp_battery = current_battery
            temp_time = current_time
            
            if len(temp_route) > 1:
                for j in range(1, len(temp_route)):
                    before_node = temp_route[j-1]
                    after_node = temp_route[j]
                    
                    # Check capacity
                    customer = node_map[customer_id]
                    if temp_load + customer.demand > vehicle.capacity:
                        continue
                    
                    # Check time window
                    travel_time_to = travel_time(node_map[before_node], node_map[customer_id], vehicle)
                    arrival_time = temp_time + travel_time_to
                    if arrival_time > customer.due_time:
                        continue
                    
                    # Check battery
                    energy_needed = get_energy(before_node, customer_id)
                    if temp_battery < energy_needed:
                        continue
                    
                    # Insert customer
                    temp_route.insert(j, customer_id)
                    new_routes[i] = temp_route
                    inserted = True
                    break
            
            if inserted:
                break
        
        if not inserted:
            # Create a new route for this customer
            new_route = [depot_id, customer_id, depot_id]
            new_routes.append(new_route)
    
    return new_routes

def improve(instance, routes, rng):
    import time
    from evrptw_autolab.problem.physics import (
        distance,
        travel_time,
        energy_required,
        full_recharge,
        propagate_route,
    )
    
    # Copy routes to avoid mutating input
    improved_routes = [list(route) for route in routes]
    
    # Precompute node data
    node_map = instance.node_map
    vehicle = instance.vehicle
    depot_id = instance.depot_id
    customer_ids = set(instance.customer_ids)
    station_ids = set(instance.station_ids)
    
    def get_distance(a, b):
        return distance(node_map[a], node_map[b])
    
    def get_energy(a, b):
        return energy_required(vehicle.consumption_rate, get_distance(a, b))
    
    def get_travel_time(a, b):
        return travel_time(vehicle.velocity, get_distance(a, b))
    
    # Check feasibility of a route
    def is_route_feasible(route):
        if not route or len(route) < 2:
            return False
        if route[0] != depot_id or route[-1] != depot_id:
            return False
        
        current_load = 0
        current_battery = vehicle.start_soc
        current_time = 0
        
        for i in range(len(route) - 1):
            node_a = route[i]
            node_b = route[i + 1]
            
            # Check capacity
            if node_a in customer_ids:
                customer = node_map[node_a]
                current_load += customer.demand
                if current_load > vehicle.capacity:
                    return False
            
            # Check battery
            energy_needed = get_energy(node_a, node_b)
            if current_battery < energy_needed:
                return False
            
            # Update battery and time
            travel_time_to = get_travel_time(node_a, node_b)
            arrival_time = current_time + travel_time_to
            
            # Check time window
            if node_b in customer_ids:
                customer = node_map[node_b]
                if arrival_time > customer.due_time:
                    return False
                
                # Wait if needed
                if arrival_time < customer.ready_time:
                    wait_time = customer.ready_time - arrival_time
                    current_time += wait_time
                    arrival_time = customer.ready_time
                
                # Update battery and time after service
                current_battery -= energy_needed
                current_time = arrival_time + customer.service_time
                current_battery += customer.service_time * vehicle.consumption_rate * vehicle.velocity
            elif node_b in station_ids:
                # Charging at station
                current_battery -= energy_needed
                
                charge_decision = full_recharge(vehicle.battery_capacity, current_battery)
                current_battery = charge_decision.new_soc
                
                current_time += vehicle.inverse_refuel_rate  # Charging time
            else:
                # Regular travel
                current_battery -= energy_needed
                current_time = arrival_time
        
        return True
    
    # Try to improve a route by swapping two customers
    def try_swap(route, i, j):
        if i == 0 or j == 0 or i == len(route) - 1 or j == len(route) - 1:
            return False  # Don't swap depot
        
        new_route = list(route)
        new_route[i], new_route[j] = new_route[j], new_route[i]
        
        if is_route_feasible(new_route):
            route[:] = new_route
            return True
        return False
    
    # Try to improve a route by moving one customer
    def try_move(route, from_idx, to_idx):
        if from_idx == 0 or from_idx == len(route) - 1:
            return False  # Don't move depot
        if to_idx == 0 or to_idx == len(route) - 1:
            return False  # Don't move to depot positions
        
        new_route = list(route)
        customer = new_route.pop(from_idx)
        new_route.insert(to_idx, customer)
        
        if is_route_feasible(new_route):
            route[:] = new_route
            return True
        return False
    
    # Try to improve a route by reordering segments
    def try_reorder(route, start, end):
        if start >= end:
            return False
        
        new_route = list(route)
        segment = new_route[start:end]
        rng.shuffle(segment)
        new_route[start:end] = segment
        
        if is_route_feasible(new_route):
            route[:] = new_route
            return True
        return False
    
    # Try to improve a route by inserting a station
    def try_insert_station(route, pos):
        if pos == 0 or pos == len(route) - 1:
            return False  # Don't insert at depot positions
        
        new_route = list(route)
        # Try to insert each station
        for station_id in station_ids:
            # Check if we can reach this station from previous node
            prev_node = new_route[pos - 1]
            energy_needed = get_energy(prev_node, station_id)
            
            # Simulate battery level at this point
            current_battery = vehicle.start_soc
            current_time = 0
            
            # Compute battery level before insertion
            for i in range(pos):
                node_a = new_route[i]
                node_b = new_route[i + 1]
                if node_a in customer_ids:
                    current_battery -= get_energy(node_a, node_b)
                elif node_a in station_ids:
                    current_battery -= get_energy(node_a, node_b)
                else:
                    current_battery -= get_energy(node_a, node_b)
                
                # Update time
                travel_time_to = get_travel_time(node_a, node_b)
                arrival_time = current_time + travel_time_to
                if node_b in customer_ids:
                    customer = node_map[node_b]
                    if arrival_time < customer.ready_time:
                        wait_time = customer.ready_time - arrival_time
                        current_time += wait_time
                        arrival_time = customer.ready_time
                    current_time = arrival_time + customer.service_time
                elif node_b in station_ids:
                    current_time += vehicle.inverse_refuel_rate
                else:
                    current_time = arrival_time
            
            if current_battery >= energy_needed:
                new_route.insert(pos, station_id)
                if is_route_feasible(new_route):
                    route[:] = new_route
                    return True
        return False
    
    # Try to reduce number of vehicles by merging routes
    def merge_routes(routes):
        if len(routes) <= 1:
            return False
        
        best_routes = list(routes)
        best_cost = sum(len(route) for route in routes)
        
        for i in range(len(routes)):
            for j in range(i + 1, len(routes)):
                route_i = routes[i]
                route_j = routes[j]
                
                if not route_i or not route_j:
                    continue
                
                # Try to merge two routes
                merged_route = route_i[:-1] + route_j[1:]
                if is_route_feasible(merged_route):
                    new_routes = [r for r in routes if r != route_i and r != route_j] + [merged_route]
                    cost = sum(len(route) for route in new_routes)
                    if cost < best_cost:
                        best_cost = cost
                        best_routes = new_routes
        
        if len(best_routes) < len(routes):
            routes[:] = best_routes
            return True
        return False
    
    # Local search improvement loop
    start_time = time.time()
    max_iterations = 1000
    iteration = 0
    
    while iteration < max_iterations and (time.time() - start_time) < 0.9:
        improved = False
        
        # Try to improve each route
        for route in improved_routes:
            if len(route) <= 2:
                continue
            
            # Try swapping customers
            for i in range(1, len(route) - 1):
                for j in range(i + 1, len(route) - 1):
                    if try_swap(route, i, j):
                        improved = True
                        break
                if improved:
                    break
            
            if not improved:
                # Try moving customers
                for i in range(1, len(route) - 1):
                    for j in range(1, len(route) - 1):
                        if i != j and try_move(route, i, j):
                            improved = True
                            break
                    if improved:
                        break
            
            if not improved:
                # Try reordering segments
                start = rng.randint(1, len(route) - 2)
                end = rng.randint(start + 1, len(route) - 1)
                if try_reorder(route, start, end):
                    improved = True
            
            if not improved:
                # Try inserting stations
                pos = rng.randint(1, len(route) - 1)
                if try_insert_station(route, pos):
                    improved = True
        
        # Try merging routes
        if not improved:
            if merge_routes(improved_routes):
                improved = True
        
        if not improved:
            break
        
        iteration += 1
    
    return improved_routes

def solve(instance, seed: int, time_limit_s: float):
    import time
    import random
    from evrptw_autolab.problem.types import CandidateSolution
    
    rng = random.Random(seed)
    start_time = time.time()
    
    # Construct initial solution
    routes = construct(instance, rng)
    
    # Repair if needed
    routes = repair(instance, routes, rng)
    
    # Improve solution
    routes = improve(instance, routes, rng)
    
    # Ensure we have time to return even if search was tight
    elapsed = time.time() - start_time
    if elapsed < time_limit_s * 0.9:
        # Optional additional search (not required by spec but can be beneficial)
        # For now, just return the improved solution
        pass
    
    return CandidateSolution(routes=routes)












