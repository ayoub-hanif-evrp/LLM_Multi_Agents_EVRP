import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import Node, VehicleSpec

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = list(instance.customer_ids)
    station_ids = list(instance.station_ids)
    vehicle = instance.vehicle
    
    # Shuffle customers to ensure randomness
    random.shuffle(customer_ids)
    
    routes = []
    current_route = [depot_id]
    current_load = 0
    current_battery = vehicle.start_soc
    current_time = 0
    
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        
        # Check if adding this customer exceeds capacity or time window
        if current_load + customer.demand > vehicle.capacity:
            # Close the current route and start a new one
            current_route.append(depot_id)
            routes.append(current_route)
            current_route = [depot_id]
            current_load = 0
            current_battery = vehicle.start_soc
            current_time = 0
        
        # Calculate travel time and energy required
        travel_dist = distance(instance.node_map[current_route[-1]], customer)
        travel_ener = energy_required(instance.node_map[current_route[-1]], customer, vehicle)
        
        if current_battery - travel_ener < 0:
            # Need to recharge
            # Find the nearest station
            nearest_station = min(station_ids, key=lambda s: distance(instance.node_map[s], instance.node_map[current_route[-1]]))
            station = instance.node_map[nearest_station]
            
            # Propagate route to the station
            stops = propagate_route(instance, current_route + [nearest_station])
            last_stop = stops[-1]
            
            # Full recharge at the station
            charge_decision = full_recharge(vehicle, last_stop.battery_arrival)
            current_battery = charge_decision.battery_departure
            current_time += charge_decision.duration
            
            # Continue to the customer
            travel_dist = distance(station, customer)
            travel_ener = energy_required(station, customer, vehicle)
        
        # Check if the customer can be served within its time window
        if current_time + travel_time(instance.node_map[current_route[-1]], customer, vehicle) + customer.service_time > customer.due_time:
            # Close the current route and start a new one
            current_route.append(depot_id)
            routes.append(current_route)
            current_route = [depot_id]
            current_load = 0
            current_battery = vehicle.start_soc
            current_time = 0
            
            # Recalculate travel time and energy required from the depot to the customer
            travel_dist = distance(instance.node_map[depot_id], customer)
            travel_ener = energy_required(instance.node_map[depot_id], customer, vehicle)
        
        # Add the customer to the current route
        current_route.append(customer_id)
        current_load += customer.demand
        current_battery -= travel_ener
        current_time += travel_time(instance.node_map[current_route[-2]], customer, vehicle) + customer.service_time
    
    # Close the last route
    if current_route:
        current_route.append(depot_id)
        routes.append(current_route)
    
    # Ensure every customer is visited exactly once
    all_customers = set(instance.customer_ids)
    visited_customers = set()
    for route in routes:
        visited_customers.update(route[1:-1])  # Exclude depot from visited customers
    
    if all_customers != visited_customers:
        raise ValueError("Not all customers are visited exactly once.")
    
    return {"routes": routes, "metadata": {}}