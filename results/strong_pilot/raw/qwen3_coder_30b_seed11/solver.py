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
        
        # Try to build a route until capacity or battery is exceeded
        while True:
            if time.time() - start_time > time_limit_s:
                break
                
            best_customer = None
            best_cost = float('inf')
            
            for customer_id in customers:
                if customer_id in visited_customers:
                    continue
                    
                customer = instance.node_map[customer_id]
                
                # Check capacity constraint
                if current_load + customer.demand > instance.vehicle.capacity:
                    continue
                    
                # Calculate travel time and energy to this customer
                prev_node = instance.node_map[route[-1]]
                travel_t = travel_time(prev_node, customer, instance.vehicle)
                energy_req = energy_required(prev_node, customer, instance.vehicle)
                
                if current_battery < energy_req:
                    continue
                    
                arrival_time = current_time + travel_t
                if arrival_time > customer.due_time:
                    continue
                    
                # Service time and battery update
                service_start = max(arrival_time, customer.ready_time)
                departure_time = service_start + customer.service_time
                
                # Check if we can return to depot with enough battery
                depot_node = instance.node_map[instance.depot_id]
                travel_back_t = travel_time(customer, depot_node, instance.vehicle)
                energy_req_back = energy_required(customer, depot_node, instance.vehicle)
                
                # Simulate battery level after serving customer and before returning to depot
                battery_after_serving = current_battery - energy_req
                if battery_after_serving < energy_req_back:
                    # Need to recharge at a station
                    nearest_station = None
                    min_dist = float('inf')
                    
                    for station_id in instance.station_ids:
                        station = instance.node_map[station_id]
                        dist = distance(customer, station)
                        if dist < min_dist:
                            min_dist = dist
                            nearest_station = station_id
                            
                    if nearest_station is not None:
                        # Check if we can reach the station and return to depot with enough battery
                        station_node = instance.node_map[nearest_station]
                        travel_to_station = travel_time(customer, station_node, instance.vehicle)
                        energy_req_to_station = energy_required(customer, station_node, instance.vehicle)
                        
                        if battery_after_serving < energy_req_to_station:
                            continue  # Not enough battery to reach station
                            
                        # Simulate charging at the station
                        charge_decision = full_recharge(instance.vehicle, battery_after_serving - energy_req_to_station)
                        battery_after_charge = charge_decision.battery_departure
                        
                        if battery_after_charge < energy_req_back:
                            continue  # Not enough battery even after charging
                    else:
                        continue  # No station available to recharge
                else:
                    battery_after_charge = battery_after_serving
                    
                # Cost function: time + distance (simplified)
                cost = travel_t + travel_back_t
                
                if cost < best_cost:
                    best_cost = cost
                    best_customer = customer_id
                    
            if best_customer is None:
                break  # No more customers can be added to this route
                
            customer = instance.node_map[best_customer]
            prev_node = instance.node_map[route[-1]]
            
            travel_t = travel_time(prev_node, customer, instance.vehicle)
            energy_req = energy_required(prev_node, customer, instance.vehicle)
            
            arrival_time = current_time + travel_t
            service_start = max(arrival_time, customer.ready_time)
            departure_time = service_start + customer.service_time
            
            # Update state
            route.append(best_customer)
            visited_customers.add(best_customer)
            current_load += customer.demand
            current_battery -= energy_req
            
            # Check if we need to recharge at a station
            depot_node = instance.node_map[instance.depot_id]
            travel_back_t = travel_time(customer, depot_node, instance.vehicle)
            energy_req_back = energy_required(customer, depot_node, instance.vehicle)
            
            if current_battery < energy_req_back:
                # Find nearest station that can provide full recharge
                nearest_station = None
                min_dist = float('inf')
                
                for station_id in instance.station_ids:
                    station = instance.node_map[station_id]
                    dist = distance(customer, station)
                    if dist < min_dist:
                        min_dist = dist
                        nearest_station = station_id
                        
                if nearest_station is not None:
                    route.append(nearest_station)
                    charge_decision = full_recharge(instance.vehicle, current_battery)
                    current_battery = charge_decision.battery_departure
                    
            # Update time and battery for next leg
            current_time = departure_time
            
        # Finalize route by appending depot if needed
        if len(route) > 1:
            route.append(instance.depot_id)
            routes.append(route)
    
    # Validate and return solution
    candidate = CandidateSolution(routes=routes)
    
    # Simple check: ensure all customers are visited exactly once
    customer_count = {}
    for r in routes:
        for node_id in r:
            if node_id in instance.customer_ids:
                customer_count[node_id] = customer_count.get(node_id, 0) + 1
                
    # Ensure no customer is missing or duplicated
    valid = True
    for cid in instance.customer_ids:
        count = customer_count.get(cid, 0)
        if count != 1:
            valid = False
            
    # Check depot positions
    for r in routes:
        if len(r) < 2 or r[0] != instance.depot_id or r[-1] != instance.depot_id:
            valid = False
            
    if not valid:
        # Return empty routes if invalid
        return {"routes": [], "metadata": {}}
        
    return {"routes": routes, "metadata": {}}



