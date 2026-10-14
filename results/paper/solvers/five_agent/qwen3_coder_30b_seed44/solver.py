import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    import random
    from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
    
    random.seed(seed)
    
    # Initialize
    customers = instance.customer_ids
    stations = instance.station_ids
    depot = instance.depot_id
    vehicle = instance.vehicle
    
    def build_routes(customers, stations, depot, vehicle):
        routes = []
        unvisited_customers = list(customers)
        
        while unvisited_customers:
            route = [depot]
            current_load = 0.0
            current_battery = vehicle.start_soc
            current_time = 0.0
            
            # Try to build a route until we can't add more customers
            while True:
                best_customer = None
                min_cost = float('inf')
                
                for customer_id in unvisited_customers:
                    customer = instance.node_map[customer_id]
                    
                    # Check if we can serve this customer
                    if (current_load + customer.demand <= vehicle.capacity):
                        # Calculate travel time and battery usage to this customer
                        travel_dist = distance(instance.node_map[route[-1]], customer)
                        travel_time_val = travel_time(instance.node_map[route[-1]], customer, vehicle)
                        energy_used = energy_required(instance.node_map[route[-1]], customer, vehicle)
                        
                        # Check if we can reach the customer within time window
                        arrival_time = current_time + travel_time_val
                        
                        if arrival_time <= customer.due_time and current_battery >= energy_used:
                            # Estimate cost (distance + time + battery usage)
                            cost = travel_dist + travel_time_val + energy_used
                            
                            if cost < min_cost:
                                min_cost = cost
                                best_customer = customer_id
                
                if best_customer is None:
                    break
                    
                # Add the best customer to route
                customer = instance.node_map[best_customer]
                route.append(best_customer)
                
                # Update state
                travel_dist = distance(instance.node_map[route[-2]], customer)
                travel_time_val = travel_time(instance.node_map[route[-2]], customer, vehicle)
                energy_used = energy_required(instance.node_map[route[-2]], customer, vehicle)
                
                current_time += travel_time_val
                current_battery -= energy_used
                current_load += customer.demand
                
                # Service the customer
                service_start = max(current_time, customer.ready_time)
                service_end = service_start + customer.service_time
                current_time = service_end
                
                # Check if we need to charge before going to depot or next customer
                energy_to_depot = energy_required(customer, instance.node_map[depot], vehicle)
                
                # If battery is insufficient to reach depot, check for charging options
                if current_battery < energy_to_depot:
                    # Find a station to recharge
                    best_station = None
                    min_dist = float('inf')
                    
                    for station_id in stations:
                        station = instance.node_map[station_id]
                        
                        # Check if we can reach the station from current location
                        if (current_battery >= energy_required(instance.node_map[route[-1]], station, vehicle)):
                            dist = distance(instance.node_map[route[-1]], station)
                            if dist < min_dist:
                                min_dist = dist
                                best_station = station_id
                    
                    if best_station is not None:
                        route.append(best_station)
                        charge_decision = full_recharge(vehicle, current_battery)
                        current_battery = charge_decision.battery_departure
                        current_time += charge_decision.duration
                        
                # Remove customer from unvisited list
                unvisited_customers.remove(best_customer)
                
            # Return to depot
            if len(route) > 1:
                route.append(depot)
                travel_dist = distance(instance.node_map[route[-2]], instance.node_map[depot])
                travel_time_val = travel_time(instance.node_map[route[-2]], instance.node_map[depot], vehicle)
                energy_used = energy_required(instance.node_map[route[-2]], instance.node_map[depot], vehicle)
                
                current_time += travel_time_val
                current_battery -= energy_used
                
            routes.append(route)
        
        return routes
    
    def insert_charges(routes, vehicle):
        """Insert charging stops into routes where necessary."""
        final_routes = []
        for route in routes:
            # Use propagate_route to compute battery states and detect need for charge
            states = propagate_route(instance, route)
            
            new_route = [route[0]]  # Start with depot
            i = 1
            while i < len(route):
                node_id = route[i]
                if node_id == depot:
                    new_route.append(node_id)
                    i += 1
                    continue
                
                # Check if we need to charge before this customer
                prev_node_id = new_route[-1]
                prev_state = states[i - 1]  # This is the state at arrival of current node
                
                # If battery is insufficient to reach next node, we must charge
                if i < len(route) - 1:  # Not the last node (which is depot)
                    next_node_id = route[i + 1]
                    energy_needed = energy_required(instance.node_map[node_id], instance.node_map[next_node_id], vehicle)
                    
                    if prev_state.battery_departure < energy_needed:
                        # Find a station to charge at
                        best_station = None
                        min_dist = float('inf')
                        for station_id in stations:
                            station = instance.node_map[station_id]
                            dist = distance(instance.node_map[node_id], station)
                            
                            # Check if we can reach the station from current location
                            if (prev_state.battery_departure >= energy_required(instance.node_map[node_id], station, vehicle) and
                                dist < min_dist):
                                min_dist = dist
                                best_station = station_id
                        
                        if best_station is not None:
                            new_route.append(best_station)
                            # Update battery after charging
                            charge_decision = full_recharge(vehicle, prev_state.battery_departure)
                            prev_state = states[i - 1]
                            prev_state.battery_departure = charge_decision.battery_departure
                            
                new_route.append(node_id)
                i += 1
            
            final_routes.append(new_route)
        
        return final_routes
    
    # Build initial routes
    routes = build_routes(customers, stations, depot, vehicle)
    
    # Post-process routes to insert charges where needed
    final_routes = insert_charges(routes, vehicle)
    
    # Validate solution
    all_customers_visited = set()
    for route in final_routes:
        for node_id in route:
            if node_id in customers:
                all_customers_visited.add(node_id)
    
    assert len(all_customers_visited) == len(customers), "Not all customers visited"
    
    # Ensure depot is only at ends
    for route in final_routes:
        assert route[0] == depot, "Route must start with depot"
        assert route[-1] == depot, "Route must end with depot"
        
    return {"routes": final_routes, "metadata": {}}



