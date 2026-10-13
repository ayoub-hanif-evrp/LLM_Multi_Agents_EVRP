import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution
from evrptw_autolab.problem.evaluator import first_fault

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initial greedy route construction
    customers = list(instance.customer_ids)
    routes = []
    unvisited = set(customers)
    
    while unvisited:
        route = [instance.depot_id]
        current_load = 0.0
        current_battery = instance.vehicle.start_soc
        current_time = 0.0
        
        # Build a route until capacity or battery is exhausted
        while True:
            best_customer = None
            min_cost = float('inf')
            
            for customer_id in list(unvisited):
                customer = instance.node_map[customer_id]
                
                # Check if we can serve this customer
                if current_load + customer.demand > instance.vehicle.capacity:
                    continue
                    
                # Calculate travel time and energy to customer
                last_node = instance.node_map[route[-1]]
                travel_t = travel_time(last_node, customer, instance.vehicle)
                energy_req = energy_required(last_node, customer, instance.vehicle)
                
                if current_battery < energy_req:
                    continue
                
                arrival_time = current_time + travel_t
                if arrival_time > customer.due_time:
                    continue
                    
                # Service time and return to depot
                service_start = max(arrival_time, customer.ready_time)
                departure_time = service_start + customer.service_time
                battery_after_service = current_battery - energy_req
                
                # Check if we can return to depot with remaining battery
                depot_node = instance.node_map[instance.depot_id]
                travel_back_t = travel_time(customer, depot_node, instance.vehicle)
                energy_back_req = energy_required(customer, depot_node, instance.vehicle)
                
                if battery_after_service < energy_back_req:
                    # Need to charge before returning
                    continue
                
                # Calculate cost (distance + time penalty)
                cost = distance(last_node, customer) + (departure_time - arrival_time)
                if cost < min_cost:
                    min_cost = cost
                    best_customer = customer_id
                    
            if best_customer is None:
                break
                
            # Add customer to route
            customer = instance.node_map[best_customer]
            last_node = instance.node_map[route[-1]]
            
            travel_t = travel_time(last_node, customer, instance.vehicle)
            energy_req = energy_required(last_node, customer, instance.vehicle)
            
            arrival_time = current_time + travel_t
            service_start = max(arrival_time, customer.ready_time)
            departure_time = service_start + customer.service_time
            
            route.append(best_customer)
            unvisited.remove(best_customer)
            current_load += customer.demand
            current_battery = current_battery - energy_req
            
            # Update time and battery
            current_time = departure_time
            current_battery = current_battery  # No change during service
            
        # Return to depot
        if len(route) > 1:
            last_node = instance.node_map[route[-1]]
            depot_node = instance.node_map[instance.depot_id]
            
            travel_t = travel_time(last_node, depot_node, instance.vehicle)
            energy_req = energy_required(last_node, depot_node, instance.vehicle)
            
            if current_battery >= energy_req:
                route.append(instance.depot_id)
                routes.append(route)
    
    # Refine routes with charging decisions
    refined_routes = []
    for route in routes:
        refined_route = refine_route_with_charging(instance, route)
        refined_routes.append(refined_route)
        
    return {"routes": refined_routes, "metadata": {}}

def refine_route_with_charging(instance, route):
    # Propagate the route to get state information
    states = propagate_route(instance, route)
    
    # Check if any charging is needed
    needs_charge = False
    for i, state in enumerate(states):
        if i == 0: continue  # Skip depot
        if state.battery_arrival < 0:
            needs_charge = True
            break
            
    if not needs_charge:
        return route
        
    # Rebuild the route with proper charging stops
    new_route = [route[0]]
    for i in range(1, len(route)):
        node_id = route[i]
        new_route.append(node_id)
        
        # Check if we need to charge before this stop
        if i < len(states) - 1:  # Not the last node (depot)
            state = states[i]
            if state.battery_arrival < 0:
                # Find a station to charge at
                best_station = find_best_station_to_charge_at(instance, route, i, state)
                if best_station:
                    new_route.append(best_station)
                    
    return new_route

def find_best_station_to_charge_at(instance, route, index, current_state):
    # Find the closest station that can provide full recharge
    best_station = None
    min_distance = float('inf')
    
    for station_id in instance.station_ids:
        station = instance.node_map[station_id]
        distance_to_station = distance(station, instance.node_map[route[index-1]])
        if distance_to_station < min_distance:
            min_distance = distance_to_station
            best_station = station_id
    
    return best_station

