import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution
from evrptw_autolab.problem.evaluator import first_fault

def solve(instance, seed: int, time_limit_s: float):
    import random
    from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
    from evrptw_autolab.problem.types import CandidateSolution
    from evrptw_autolab.problem.evaluator import first_fault
    
    random.seed(seed)
    
    # Precompute all distances for efficiency
    dist_cache = {}
    all_nodes = [instance.depot_id] + list(instance.customer_ids) + list(instance.station_ids)
    for a in all_nodes:
        for b in all_nodes:
            if (a, b) not in dist_cache:
                dist_cache[(a, b)] = distance(instance.node_map[a], instance.node_map[b])
    
    def get_distance(a, b):
        return dist_cache.get((a, b), dist_cache.get((b, a), 0.0))
    
    # Helper to check if a route is feasible
    def is_route_feasible(route):
        try:
            states = propagate_route(instance, route)
            # Check that all stops are valid
            for state in states:
                if state.battery_arrival < 0:
                    return False
            return True
        except Exception:
            return False
    
    # Helper to compute total distance of a route
    def route_distance(route):
        dist = 0.0
        for i in range(len(route) - 1):
            dist += get_distance(route[i], route[i+1])
        return dist
    
    # Greedy construction with proper battery tracking
    routes = []
    unvisited_customers = list(instance.customer_ids)
    
    while unvisited_customers:
        route = [instance.depot_id]
        current_load = 0.0
        current_battery = instance.vehicle.start_soc
        current_time = 0.0
        
        # Try to build a route until no more customers can be added
        while True:
            best_customer = None
            best_insertion_cost = float('inf')
            
            for customer_id in unvisited_customers:
                customer = instance.node_map[customer_id]
                
                # Check if we can reach this customer
                last_node = instance.node_map[route[-1]]
                travel_dist = get_distance(route[-1], customer_id)
                energy_needed = energy_required(last_node, customer, instance.vehicle)
                
                if current_battery < energy_needed:
                    continue  # Not enough battery to reach customer
                
                # Check time window
                arrival_time = current_time + travel_time(last_node, customer, instance.vehicle)
                if arrival_time > customer.due_time:
                    continue  # Too late
                
                # Calculate service start and departure times
                service_start = max(arrival_time, customer.ready_time)
                departure_time = service_start + customer.service_time
                
                # Check if we can return to depot with enough battery
                depot_node = instance.node_map[instance.depot_id]
                return_dist = get_distance(customer_id, instance.depot_id)
                return_energy_needed = energy_required(customer, depot_node, instance.vehicle)
                
                if current_battery - energy_needed - return_energy_needed < 0:
                    continue  # Not enough battery to return to depot
                
                # Compute cost (distance + time penalty for late arrival)
                cost = travel_dist + max(0, arrival_time - customer.due_time) * 1000
                
                if cost < best_insertion_cost:
                    best_insertion_cost = cost
                    best_customer = customer_id
            
            if best_customer is None:
                # No more customers can be added to this route
                break
            
            # Add the best customer to the route
            customer = instance.node_map[best_customer]
            last_node = instance.node_map[route[-1]]
            
            travel_dist = get_distance(route[-1], best_customer)
            energy_needed = energy_required(last_node, customer, instance.vehicle)
            
            arrival_time = current_time + travel_time(last_node, customer, instance.vehicle)
            service_start = max(arrival_time, customer.ready_time)
            departure_time = service_start + customer.service_time
            
            # Update state
            current_battery -= energy_needed
            current_load += customer.demand
            current_time = departure_time
            
            route.append(best_customer)
            unvisited_customers.remove(best_customer)
            
            # Check if we need to charge before next stop
            if current_battery < 0.1 * instance.vehicle.battery_capacity:
                # Find nearest station that allows us to continue
                nearest_station = None
                min_dist = float('inf')
                
                for station_id in instance.station_ids:
                    station = instance.node_map[station_id]
                    dist = get_distance(best_customer, station_id)
                    if dist < min_dist:
                        min_dist = dist
                        nearest_station = station_id
                
                if nearest_station is not None:
                    # Add charging visit
                    route.append(nearest_station)
                    charge_decision = full_recharge(instance.vehicle, current_battery)
                    current_battery = charge_decision.battery_departure
                    current_time += charge_decision.duration
        
        # Return to depot
        last_node = instance.node_map[route[-1]]
        depot_node = instance.node_map[instance.depot_id]
        travel_dist = get_distance(route[-1], instance.depot_id)
        energy_needed = energy_required(last_node, depot_node, instance.vehicle)
        
        if current_battery >= energy_needed:
            arrival_time = current_time + travel_time(last_node, depot_node, instance.vehicle)
            route.append(instance.depot_id)
            routes.append(route)
        else:
            # If we can't return to depot, abandon this route and try again
            continue
    
    # Final validation of the solution
    if not routes:
        # If no routes were formed, create a single empty route
        routes = [[instance.depot_id]]
    
    # Validate solution structure
    all_customers_visited = set()
    for route in routes:
        if not route or route[0] != instance.depot_id or route[-1] != instance.depot_id:
            # Invalid route structure
            return {"routes": [[instance.depot_id]], "metadata": {}}
        
        for node_id in route:
            if node_id in instance.customer_ids:
                all_customers_visited.add(node_id)
    
    # Ensure all customers are visited exactly once
    if len(all_customers_visited) != instance.n_customers:
        # Reconstruct with a simple greedy approach that ensures coverage
        routes = []
        unvisited_customers = list(instance.customer_ids)
        
        while unvisited_customers:
            route = [instance.depot_id]
            current_load = 0.0
            current_battery = instance.vehicle.start_soc
            current_time = 0.0
            
            # Add customers greedily
            while True:
                best_customer = None
                min_cost = float('inf')
                
                for customer_id in unvisited_customers:
                    customer = instance.node_map[customer_id]
                    
                    last_node = instance.node_map[route[-1]]
                    travel_dist = get_distance(route[-1], customer_id)
                    energy_needed = energy_required(last_node, customer, instance.vehicle)
                    
                    if current_battery < energy_needed:
                        continue
                    
                    arrival_time = current_time + travel_time(last_node, customer, instance.vehicle)
                    if arrival_time > customer.due_time:
                        continue
                    
                    service_start = max(arrival_time, customer.ready_time)
                    departure_time = service_start + customer.service_time
                    
                    # Check return to depot
                    depot_node = instance.node_map[instance.depot_id]
                    return_dist = get_distance(customer_id, instance.depot_id)
                    return_energy_needed = energy_required(customer, depot_node, instance.vehicle)
                    
                    if current_battery - energy_needed - return_energy_needed < 0:
                        continue
                    
                    cost = travel_dist + max(0, arrival_time - customer.due_time) * 1000
                    
                    if cost < min_cost:
                        min_cost = cost
                        best_customer = customer_id
                
                if best_customer is None:
                    break
                
                customer = instance.node_map[best_customer]
                last_node = instance.node_map[route[-1]]
                
                travel_dist = get_distance(route[-1], best_customer)
                energy_needed = energy_required(last_node, customer, instance.vehicle)
                
                arrival_time = current_time + travel_time(last_node, customer, instance.vehicle)
                service_start = max(arrival_time, customer.ready_time)
                departure_time = service_start + customer.service_time
                
                current_battery -= energy_needed
                current_load += customer.demand
                current_time = departure_time
                
                route.append(best_customer)
                unvisited_customers.remove(best_customer)
                
                # Check for charging needs
                if current_battery < 0.1 * instance.vehicle.battery_capacity:
                    nearest_station = None
                    min_dist = float('inf')
                    
                    for station_id in instance.station_ids:
                        station = instance.node_map[station_id]
                        dist = get_distance(best_customer, station_id)
                        if dist < min_dist:
                            min_dist = dist
                            nearest_station = station_id
                    
                    if nearest_station is not None:
                        route.append(nearest_station)
                        charge_decision = full_recharge(instance.vehicle, current_battery)
                        current_battery = charge_decision.battery_departure
                        current_time += charge_decision.duration
            
            # Return to depot
            last_node = instance.node_map[route[-1]]
            depot_node = instance.node_map[instance.depot_id]
            travel_dist = get_distance(route[-1], instance.depot_id)
            energy_needed = energy_required(last_node, depot_node, instance.vehicle)
            
            if current_battery >= energy_needed:
                arrival_time = current_time + travel_time(last_node, depot_node, instance.vehicle)
                route.append(instance.depot_id)
                routes.append(route)
            else:
                # If we can't return to depot, abandon this route
                continue
    
    # Final check for validity
    packet = first_fault(instance, CandidateSolution(routes=routes))
    if packet["family"] != "OK":
        # Return a valid but minimal solution
        routes = [[instance.depot_id]]
    
    # Compute total distance for metadata
    total_distance = 0.0
    for route in routes:
        total_distance += route_distance(route)
    
    return {"routes": routes, "metadata": {"total_distance": total_distance}}

