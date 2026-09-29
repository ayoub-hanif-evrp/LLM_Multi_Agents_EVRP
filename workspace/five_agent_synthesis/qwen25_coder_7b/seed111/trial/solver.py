import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes
    routes = [[] for _ in range(instance.n_customers)]
    depot_id = instance.depot_id
    customers = instance.customer_ids
    
    # Assign customers to routes
    for customer in customers:
        # Find the nearest station
        nearest_station = min(instance.station_ids, key=lambda station: distance(instance.node_map[customer], instance.node_map[station]))
        # Add customer to the route that has the least distance to the nearest station
        min_distance = float('inf')
        min_route_index = -1
        for i, route in enumerate(routes):
            if route:
                last_node = route[-1]
                dist = distance(instance.node_map[last_node], instance.node_map[nearest_station]) + distance(instance.node_map[nearest_station], instance.node_map[customer])
                if dist < min_distance:
                    min_distance = dist
                    min_route_index = i
        routes[min_route_index].append(customer)
    
    # Add depot to the start and end of each route
    for i, route in enumerate(routes):
        routes[i] = [depot_id] + route + [depot_id]
    
    # Apply charging policy to each route
    for i, route in enumerate(routes):
        routes[i] = charging_policy(instance, route)
    
    # Return the solution
    return {"routes": routes, "metadata": {}}

def charging_policy(instance, route):
    vehicle = instance.vehicle
    for i, node_id in enumerate(route):
        if node_id in instance.station_ids:
            stop_state = propagate_route(instance, route[:i+1])[-1]
            battery_arrival = stop_state.battery_departure
            energy_required = energy_required(instance.node_map[node_id], instance.node_map[route[i+1]], vehicle)
            charge_decision = full_recharge(vehicle, battery_arrival)
            if charge_decision.energy_charged < energy_required:
                # Handle insufficient energy by recharging to full capacity
                charge_decision = full_recharge(vehicle, battery_arrival)
                stop_state.battery_departure = charge_decision.battery_departure
                stop_state.energy_charged = charge_decision.energy_charged
    return route