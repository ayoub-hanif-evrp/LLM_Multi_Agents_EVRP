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
    vehicle = instance.vehicle
    
    # Shuffle customers for randomness
    rng.shuffle(customer_ids)
    
    routes = []
    visited_customers = set()
    
    while len(visited_customers) < len(customer_ids):
        route = [depot_id]
        current_load = 0
        current_time = 0
        current_battery = vehicle.start_soc
        
        # Try to build a route until no more customers can be added
        while True:
            best_customer = None
            best_score = float('inf')
            
            # Find the next customer that can be served
            for customer_id in customer_ids:
                if customer_id in visited_customers:
                    continue
                
                customer = instance.node_map[customer_id]
                
                # Check capacity constraint
                if current_load + customer.demand > vehicle.capacity:
                    continue
                
                # Check time window
                if current_time > customer.due_time:
                    continue
                
                # Check battery constraint
                last_node = instance.node_map[route[-1]]
                dist = distance(last_node, customer)
                energy_needed = energy_required(last_node, customer, vehicle)
                
                if current_battery < energy_needed:
                    continue
                
                # Score based on proximity and time window tightness
                travel_time_val = travel_time(dist, vehicle)
                arrival_time = current_time + travel_time_val
                
                if arrival_time > customer.due_time:
                    continue  # Cannot serve within time window
                
                score = dist + (max(0, arrival_time - customer.ready_time) * 10)
                if score < best_score:
                    best_score = score
                    best_customer = customer_id
            
            if best_customer is None:
                break
            
            # Add the customer to the route
            customer = instance.node_map[best_customer]
            last_node = instance.node_map[route[-1]]
            dist = distance(last_node, customer)
            energy_needed = energy_required(last_node, customer, vehicle)
            
            current_time += travel_time(dist, vehicle)
            current_battery -= energy_needed
            
            # Service time at the customer
            if current_time < customer.ready_time:
                current_time = customer.ready_time
            
            current_time += customer.service_time
            current_load += customer.demand
            
            route.append(best_customer)
            visited_customers.add(best_customer)
        
        # Return to depot
        if len(route) > 1:
            last_node = instance.node_map[route[-1]]
            depot = instance.node_map[depot_id]
            dist = distance(last_node, depot)
            energy_needed = energy_required(last_node, depot, vehicle)
            
            current_time += travel_time(dist, vehicle)
            current_battery -= energy_needed
            
            # Recharge if needed before returning to depot
            if current_battery < 0:
                recharge_needed = -current_battery
                charge_decision = full_recharge(recharge_needed, vehicle.inverse_refuel_rate)
                current_time += charge_decision.duration
                current_battery = vehicle.battery_capacity
                
                # Add charging station to route
                for station_id in instance.station_ids:
                    if station_id not in route:
                        route.append(station_id)
                        break
            
            route.append(depot_id)
            routes.append(route)
        else:
            break
    
    return routes

def repair(instance, routes, rng):
    depot_id = instance.depot_id
    customer_ids = set(instance.customer_ids)
    station_ids = set(instance.station_ids)
    vehicle = instance.vehicle
    
    # Collect all visited customers and validate depot placement
    visited_customers = set()
    new_routes = []
    
    for route in routes:
        if not route or len(route) < 2:
            continue
        
        # Ensure depot is at start and end
        if route[0] != depot_id or route[-1] != depot_id:
            new_route = [depot_id]
            for node_id in route:
                if node_id == depot_id:
                    continue
                new_route.append(node_id)
            new_route.append(depot_id)
        else:
            new_route = route[:]
        
        # Process stops to fix capacity, time windows, battery
        processed_route = [depot_id]
        load = 0
        time = 0
        battery = vehicle.start_soc
        
        for node_id in new_route[1:-1]:
            if node_id in customer_ids:
                customer = instance.node_map[node_id]
                
                # Check if we can serve this customer
                last_node = instance.node_map[processed_route[-1]]
                dist = distance(last_node, customer)
                energy_needed = energy_required(vehicle.consumption_rate, dist)
                
                # Ensure battery is sufficient for travel and service
                if battery < energy_needed:
                    # Recharge before serving customer
                    recharge_needed = energy_needed - battery
                    charge_decision = full_recharge(recharge_needed, vehicle.inverse_refuel_rate)
                    time += charge_decision.duration
                    battery = vehicle.battery_capacity
                    
                    # Add charging station to route
                    for station_id in station_ids:
                        if station_id not in processed_route:
                            processed_route.append(station_id)
                            break
                
                # Travel to customer
                time += travel_time(vehicle, dist)  # Fixed: was vehicle.velocity
                battery -= energy_needed
                
                # Check time window
                if time > customer.due_time:
                    continue  # Skip this customer
                
                # Serve customer
                if time < customer.ready_time:
                    time = customer.ready_time
                
                time += customer.service_time
                load += customer.demand
                
                processed_route.append(node_id)
                visited_customers.add(node_id)
            elif node_id in station_ids:
                # Add charging station to route
                processed_route.append(node_id)
        
        # Return to depot
        if len(processed_route) > 1:
            last_node = instance.node_map[processed_route[-1]]
            depot = instance.node_map[depot_id]
            dist = distance(last_node, depot)
            energy_needed = energy_required(vehicle.consumption_rate, dist)
            
            time += travel_time(vehicle, dist)  # Fixed: was vehicle.velocity
            battery -= energy_needed
            
            # Recharge if needed
            if battery < 0:
                recharge_needed = -battery
                charge_decision = full_recharge(recharge_needed, vehicle.inverse_refuel_rate)
                time += charge_decision.duration
                battery = vehicle.battery_capacity
                
                # Add charging station in route
                for station_id in station_ids:
                    if station_id not in processed_route:
                        processed_route.append(station_id)
                        break
            
            processed_route.append(depot_id)
            new_routes.append(processed_route)
    
    # Handle missing customers by adding them to existing routes or creating new ones
    missing_customers = customer_ids - visited_customers
    for cust_id in missing_customers:
        added = False
        customer = instance.node_map[cust_id]
        
        # Try to add to an existing route
        for i, route in enumerate(new_routes):
            if len(route) < 2:
                continue
            
            last_node = instance.node_map[route[-2]]
            dist = distance(last_node, customer)
            energy_needed = energy_required(vehicle.consumption_rate, dist)
            
            # Check capacity and battery constraints
            if (customer.demand + sum(instance.node_map[n].demand for n in route[1:-1]) <= vehicle.capacity and
                energy_needed <= vehicle.battery_capacity):
                
                new_routes[i] = route[:-1] + [cust_id, depot_id]
                added = True
                break
        
        if not added:
            # Create a new route for this customer
            new_routes.append([depot_id, cust_id, depot_id])
    
    return new_routes

def improve(instance, routes, rng):
    import time
    
    depot_id = instance.depot_id
    customer_ids = set(instance.customer_ids)
    station_ids = set(instance.station_ids)
    vehicle = instance.vehicle
    
    # Make a copy of routes to avoid mutating input
    improved_routes = [route[:] for route in routes]
    
    # Local search improvement loop with finite iterations
    max_iterations = 50
    iteration = 0
    
    while iteration < max_iterations:
        improved = False
        
        # Try 2-opt style moves between routes
        for i in range(len(improved_routes)):
            route1 = improved_routes[i]
            if len(route1) < 3:  # Need at least depot, customer, depot
                continue
            
            for j in range(i + 1, len(improved_routes)):
                route2 = improved_routes[j]
                if len(route2) < 3:
                    continue
                
                # Try moving a customer from route2 to route1
                for k in range(1, len(route2) - 1):  # Skip depot
                    cust_id = route2[k]
                    
                    # Check if we can move this customer to route1
                    if cust_id not in customer_ids:
                        continue
                    
                    customer = instance.node_map[cust_id]
                    
                    # Try inserting into route1
                    for pos in range(1, len(route1)):  # Skip depot
                        # Check capacity
                        load1 = sum(instance.node_map[n].demand for n in route1[1:pos]) + \
                                sum(instance.node_map[n].demand for n in route1[pos:-1]) + customer.demand
                        if load1 > vehicle.capacity:
                            continue
                        
                        # Check battery feasibility
                        try:
                            # Simulate inserting customer at pos in route1
                            test_route = route1[:pos] + [cust_id] + route1[pos:]
                            
                            # Propagate the route to check feasibility
                            result = propagate_route(instance, test_route, vehicle)
                            if result.is_feasible:
                                # Check if moving customer improves total distance
                                original_distance = sum(distance(instance.node_map[test_route[m]], instance.node_map[test_route[m+1]])
                                                       for m in range(len(test_route)-1))
                                
                                # Try removing from route2 and check if it's better
                                new_route2 = route2[:k] + route2[k+1:]
                                test_route2 = [depot_id] + new_route2 + [depot_id]
                                
                                result2 = propagate_route(instance, test_route2, vehicle)
                                if result2.is_feasible:
                                    # If both are feasible, check if total distance improves
                                    new_distance = sum(distance(instance.node_map[test_route[m]], instance.node_map[test_route[m+1]])
                                                      for m in range(len(test_route)-1))
                                    
                                    if new_distance < original_distance:
                                        improved_routes[i] = test_route
                                        improved_routes[j] = new_route2 + [depot_id]
                                        improved = True
                        except Exception:
                            continue
                
                if improved:
                    break
            
            if improved:
                break
        
        if not improved:
            break
        
        iteration += 1
    
    # Ensure all customers are visited exactly once
    visited_customers = set()
    for route in improved_routes:
        for node_id in route:
            if node_id in customer_ids:
                visited_customers.add(node_id)
    
    # Add missing customers to new routes
    missing_customers = customer_ids - visited_customers
    for cust_id in missing_customers:
        # Find a route to insert this customer into
        added = False
        for i, route in enumerate(improved_routes):
            if len(route) < 2:
                continue
            
            # Try inserting at the end before depot
            last_node = instance.node_map[route[-2]]
            customer = instance.node_map[cust_id]
            dist = distance(last_node, customer)
            energy_needed = energy_required(vehicle.consumption_rate, dist)
            
            if (customer.demand + sum(instance.node_map[n].demand for n in route[1:-1]) <= vehicle.capacity and
                energy_needed <= vehicle.battery_capacity):
                improved_routes[i] = route[:-1] + [cust_id, depot_id]
                added = True
                break
        
        if not added:
            # Create a new route for this customer
            improved_routes.append([depot_id, cust_id, depot_id])
    
    return improved_routes

def solve(instance, seed: int, time_limit_s: float):
    import random
    import time
    
    rng = random.Random(seed)
    start_time = time.time()
    
    # Construct initial solution
    routes = construct(instance, rng)
    
    # Repair solution to ensure all customers are visited
    routes = repair(instance, routes, rng)
    
    # Improve solution
    routes = improve(instance, routes, rng)
    
    # Check time limit and perform additional improvement if time remains
    elapsed = time.time() - start_time
    if elapsed < time_limit_s * 0.8:
        # Perform one more round of improvement with more iterations
        routes = improve(instance, routes, rng)
    
    # Return solution
    return CandidateSolution(routes=routes)
















