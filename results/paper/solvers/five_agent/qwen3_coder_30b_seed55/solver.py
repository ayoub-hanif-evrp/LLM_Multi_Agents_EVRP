import random
from typing import List, Tuple, Optional
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import EVRPTWInstance, CandidateSolution

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> dict:
    random.seed(seed)
    
    # Initial construction: assign customers to routes greedily
    customers = list(instance.customer_ids)
    routes = []
    unassigned = set(customers)
    
    while unassigned:
        route = [instance.depot_id]
        current_load = 0.0
        current_battery = instance.vehicle.start_soc
        current_time = 0.0
        
        # Try to add customers to the current route
        while True:
            best_customer = None
            best_cost = float('inf')
            
            for customer_id in unassigned:
                customer = instance.node_map[customer_id]
                
                # Check if we can reach this customer
                last_node = instance.node_map[route[-1]]
                travel_dist = distance(last_node, customer)
                energy_needed = energy_required(last_node, customer, instance.vehicle)
                
                if current_battery >= energy_needed:
                    # Check time window
                    arrival_time = current_time + travel_time(last_node, customer, instance.vehicle)
                    if arrival_time <= customer.due_time:
                        # Calculate cost (distance + service time)
                        cost = travel_dist + customer.service_time
                        
                        if cost < best_cost:
                            best_cost = cost
                            best_customer = customer_id
            
            if best_customer is None:
                break
                
            # Add the customer to route
            customer = instance.node_map[best_customer]
            last_node = instance.node_map[route[-1]]
            
            travel_dist = distance(last_node, customer)
            energy_needed = energy_required(last_node, customer, instance.vehicle)
            
            arrival_time = current_time + travel_time(last_node, customer, instance.vehicle)
            service_start = max(arrival_time, customer.ready_time)
            departure_time = service_start + customer.service_time
            
            # Update state
            current_battery -= energy_needed
            current_load += customer.demand
            current_time = departure_time
            
            route.append(best_customer)
            unassigned.remove(best_customer)
            
        # Check if we need to recharge before returning to depot
        last_node = instance.node_map[route[-1]]
        travel_dist = distance(last_node, instance.depot)
        energy_needed = energy_required(last_node, instance.depot, instance.vehicle)
        
        # Ensure we have enough battery to return to depot
        if current_battery >= energy_needed:
            route.append(instance.depot_id)
            routes.append(route)
        else:
            # If cannot return to depot, check if we can recharge before returning
            # Find the nearest station to recharge before returning
            best_station = None
            min_dist = float('inf')
            
            for station_id in instance.station_ids:
                station = instance.node_map[station_id]
                dist = distance(last_node, station)
                if dist < min_dist:
                    min_dist = dist
                    best_station = station_id
            
            if best_station is not None:
                # Recharge at the station before returning to depot
                route.append(best_station)
                charge_decision = full_recharge(instance.vehicle, current_battery)
                current_battery = charge_decision.battery_departure
                current_time += charge_decision.duration
                
                # Now try to return to depot
                last_node = instance.node_map[route[-1]]
                travel_dist = distance(last_node, instance.depot)
                energy_needed = energy_required(last_node, instance.depot, instance.vehicle)
                
                if current_battery >= energy_needed:
                    arrival_time = current_time + travel_time(last_node, instance.depot, instance.vehicle)
                    route.append(instance.depot_id)
                    routes.append(route)
                else:
                    # If still cannot return to depot, skip this route
                    pass
            else:
                # No station found to recharge before returning
                pass
    
    # Final validation and optimization
    valid_routes = []
    for route in routes:
        if len(route) < 3:
            continue  # Skip empty or invalid routes
            
        # Validate that all customers are visited exactly once
        customer_count = {}
        for node_id in route:
            node = instance.node_map[node_id]
            if node.kind == 'customer':
                customer_count[node_id] = customer_count.get(node_id, 0) + 1
                
        if all(count == 1 for count in customer_count.values()):
            valid_routes.append(route)
    
    # Ensure depot is only at ends
    final_routes = []
    for route in valid_routes:
        if route[0] != instance.depot_id or route[-1] != instance.depot_id:
            continue
        final_routes.append(route)
        
    # If any customers are missing, try to reassign them
    assigned_customers = set()
    for route in final_routes:
        for node_id in route:
            node = instance.node_map[node_id]
            if node.kind == 'customer':
                assigned_customers.add(node_id)
    
    missing_customers = set(instance.customer_ids) - assigned_customers
    if missing_customers:
        # Reassign missing customers to new routes
        for customer_id in missing_customers:
            route = [instance.depot_id]
            customer = instance.node_map[customer_id]
            route.append(customer_id)
            route.append(instance.depot_id)
            final_routes.append(route)
    
    return {"routes": final_routes, "metadata": {}}



