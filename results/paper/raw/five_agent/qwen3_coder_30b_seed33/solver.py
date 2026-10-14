import random
import time
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    import random
    import time
    from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
    from evrptw_autolab.problem.types import CandidateSolution
    
    random.seed(seed)
    start_time = time.time()
    
    # Initial construction: assign customers to routes greedily
    customers = list(instance.customer_ids)
    random.shuffle(customers)
    
    routes = []
    visited_customers = set()
    
    while len(visited_customers) < instance.n_customers:
        if time.time() - start_time > time_limit_s:
            break
            
        route = [instance.depot_id]
        current_load = 0
        current_battery = instance.vehicle.start_soc
        current_time = 0.0
        
        # Try to add customers to the current route
        customer_added = True
        while customer_added and len(visited_customers) < instance.n_customers:
            customer_added = False
            best_customer = None
            best_insertion_cost = float('inf')
            
            for cust_id in customers:
                if cust_id in visited_customers:
                    continue
                    
                # Check if we can visit this customer
                node = instance.node_map[cust_id]
                prev_node = instance.node_map[route[-1]]
                
                travel_dist = distance(prev_node, node)
                travel_time_cost = travel_time(prev_node, node, instance.vehicle)
                energy_needed = energy_required(prev_node, node, instance.vehicle)
                
                if current_battery < energy_needed:
                    continue
                    
                # Check time window
                arrival_time = current_time + travel_time_cost
                if arrival_time > node.due_time:
                    continue
                    
                service_start = max(arrival_time, node.ready_time)
                departure_time = service_start + node.service_time
                
                # Check if we can return to depot with enough battery
                depot_node = instance.node_map[instance.depot_id]
                return_dist = distance(node, depot_node)
                return_energy_needed = energy_required(node, depot_node, instance.vehicle)
                
                if current_battery - energy_needed - return_energy_needed < 0:
                    continue
                    
                # Calculate insertion cost (simplified: just travel time + service time)
                cost = travel_time_cost + node.service_time
                
                if cost < best_insertion_cost:
                    best_insertion_cost = cost
                    best_customer = cust_id
            
            if best_customer is not None:
                route.append(best_customer)
                visited_customers.add(best_customer)
                customer_added = True
                
                # Update state
                prev_node = instance.node_map[route[-2]]
                node = instance.node_map[best_customer]
                
                travel_dist = distance(prev_node, node)
                travel_time_cost = travel_time(prev_node, node, instance.vehicle)
                energy_needed = energy_required(prev_node, node, instance.vehicle)
                
                current_time += travel_time_cost
                arrival_time = current_time
                service_start = max(arrival_time, node.ready_time)
                departure_time = service_start + node.service_time
                
                current_battery -= energy_needed
                current_load += node.demand
                current_time = departure_time
                
                # Check if we need to charge
                if current_battery < 0.1 * instance.vehicle.battery_capacity:
                    # Find nearest station and insert charge
                    best_station = None
                    min_dist = float('inf')
                    for station_id in instance.station_ids:
                        station_node = instance.node_map[station_id]
                        dist = distance(node, station_node)
                        if dist < min_dist:
                            min_dist = dist
                            best_station = station_id
                    
                    if best_station is not None:
                        route.append(best_station)
                        charge_decision = full_recharge(instance.vehicle, current_battery)
                        current_battery = charge_decision.battery_departure
                        current_time += charge_decision.duration
        
        # Return to depot
        if len(route) > 1:
            route.append(instance.depot_id)
            last_node = instance.node_map[route[-2]]
            depot_node = instance.node_map[instance.depot_id]
            
            travel_dist = distance(last_node, depot_node)
            travel_time_cost = travel_time(last_node, depot_node, instance.vehicle)
            energy_needed = energy_required(last_node, depot_node, instance.vehicle)
            
            current_time += travel_time_cost
            current_battery -= energy_needed
            
            routes.append(route)
    
    # Final validation and optimization
    valid_routes = []
    for route in routes:
        if len(route) < 3:  # Need at least depot -> customer -> depot
            continue
            
        # Check that route starts and ends at depot
        if route[0] != instance.depot_id or route[-1] != instance.depot_id:
            continue
            
        # Check for internal depots
        if any(node == instance.depot_id for node in route[1:-1]):
            continue
            
        valid_routes.append(route)
    
    # Reconstruct routes to ensure feasibility
    final_routes = []
    for route in valid_routes:
        try:
            states = propagate_route(instance, route)
            # If we get here without exception, the route is valid
            final_routes.append(route)
        except Exception:
            continue
    
    return {"routes": final_routes, "metadata": {}}

