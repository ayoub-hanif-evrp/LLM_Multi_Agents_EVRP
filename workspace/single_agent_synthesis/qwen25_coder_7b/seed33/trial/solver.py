from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    vehicle = instance.vehicle
    capacity = vehicle.capacity
    battery_capacity = vehicle.battery_capacity
    consumption_rate = vehicle.consumption_rate
    
    routes = [[depot_id]]
    for customer_id in customer_ids:
        routes[0].append(customer_id)
    routes[0].append(depot_id)
    
    # Check for charging feasibility
    for i in range(1, len(routes[0]) - 1):
        current_node = instance.node_map[routes[0][i]]
        next_node = instance.node_map[routes[0][i + 1]]
        energy_needed = energy_required(current_node, next_node, vehicle)
        if energy_needed > battery_capacity:
            # Insert a charging station before the current node
            for station_id in instance.station_ids:
                station = instance.node_map[station_id]
                if energy_required(station, current_node, vehicle) <= battery_capacity:
                    routes[0].insert(i, station_id)
                    break
    
    # Propagate the route to check for feasibility
    states = propagate_route(instance, routes[0])
    for state in states:
        if state.battery_arrival < 0:
            # Handle negative battery arrival by full recharging
            state.battery_arrival = full_recharge(vehicle, state.battery_arrival)
    
    return {"routes": routes, "metadata": {}}