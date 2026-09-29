from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    vehicle = instance.vehicle
    
    # Initialize routes with the depot
    routes = [[depot_id] for _ in range(len(customers) + 1)]
    
    # Assign customers to routes
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        min_distance = float('inf')
        best_route_index = -1
        
        for i, route in enumerate(routes):
            if len(route) > 1 and route[-1] == depot_id:
                continue
            last_node = instance.node_map[route[-1]]
            dist = distance(last_node, customer)
            if dist < min_distance:
                min_distance = dist
                best_route_index = i
        
        if best_route_index == -1:
            # If no valid route found, create a new one
            routes.append([depot_id, customer_id, depot_id])
        else:
            routes[best_route_index].append(customer_id)
    
    # Ensure the depot is at the end of each route
    for route in routes:
        if route[-1] != depot_id:
            route.append(depot_id)
    
    # Check for feasibility and fix issues
    for i, route in enumerate(routes):
        if len(route) > 1:
            states = propagate_route(instance, route)
            for j, state in enumerate(states):
                if state.battery_arrival < 0:
                    # Full recharge at the last station before the fault
                    last_station = instance.node_map[route[j-1]]
                    new_state = full_recharge(vehicle, state.battery_arrival)
                    new_state.service_start = state.service_start
                    new_state.arrival_time = state.arrival_time
                    new_state.load = state.load
                    new_state.battery_departure = state.battery_departure
                    states[j] = new_state
                if state.service_start > instance.node_map[route[j]].due_time:
                    # Adjust service start time to fit the window
                    new_state = state._replace(service_start=instance.node_map[route[j]].due_time)
                    new_state.arrival_time = new_state.service_start + travel_time(instance.node_map[route[j]], instance.node_map[route[j+1]], vehicle)
                    states[j] = new_state
    
    # Return the solution
    return {"routes": routes, "metadata": {}}