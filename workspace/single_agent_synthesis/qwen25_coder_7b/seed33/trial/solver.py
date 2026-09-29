from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    vehicle = instance.vehicle
    
    # Initialize routes
    routes = [[depot_id]]
    
    # Add customers to routes
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        if len(routes[-1]) + 1 > vehicle.capacity:
            routes.append([depot_id])
        routes[-1].append(customer_id)
    
    routes[-1].append(depot_id)
    
    # Apply charging logic
    for route_index, route in enumerate(routes):
        if route_index == 0:
            continue  # Skip depot route
        for i in range(1, len(route) - 1):
            current_node = instance.node_map[route[i]]
            previous_node = instance.node_map[route[i - 1]]
            next_node = instance.node_map[route[i + 1]]
            
            state = propagate_route(instance, route[:i + 1])
            battery_arrival = state[-1].battery_departure
            energy_needed = energy_required(previous_node, current_node, vehicle)
            
            if battery_arrival < energy_needed:
                recharge_decision = full_recharge(vehicle, battery_arrival)
                energy_charged = recharge_decision.energy_charged
                duration = recharge_decision.duration
                battery_departure = recharge_decision.battery_departure
                
                # Insert recharge station
                recharge_station_id = instance.station_ids[0]  # Assuming one station for simplicity
                routes[route_index].insert(i, recharge_station_id)
                routes[route_index].insert(i + 1, recharge_station_id)
                
                # Update state with recharge
                state = propagate_route(instance, routes[route_index])
                battery_arrival = state[-1].battery_departure
                
                # Adjust route to account for recharge
                routes[route_index] = [depot_id] + [node_id for node_id, state in zip(routes[route_index], state) if node_id != recharge_station_id] + [depot_id]
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {}
    }