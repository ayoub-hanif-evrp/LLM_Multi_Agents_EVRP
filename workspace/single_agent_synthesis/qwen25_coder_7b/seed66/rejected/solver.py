from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    vehicle = instance.vehicle
    
    # Initialize routes with the depot
    routes = [[depot_id] for _ in range(len(customers))]
    
    # Assign customers to routes
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        min_cost = float('inf')
        best_route_index = -1
        
        for i, route in enumerate(routes):
            if len(route) == 1:
                cost = distance(instance.node_map[route[-1]], customer) + distance(customer, instance.depot)
            else:
                cost = distance(instance.node_map[route[-1]], customer)
            
            if cost < min_cost:
                min_cost = cost
                best_route_index = i
        
        routes[best_route_index].append(customer_id)
    
    # Add the depot to the end of each route
    for i in range(len(routes)):
        routes[i].append(depot_id)
    
    # Check for charging requirements and apply full recharge
    for i, route in enumerate(routes):
        states = propagate_route(instance, route)
        for j in range(len(states) - 1):
            current_state = states[j]
            next_state = states[j + 1]
            if current_state.battery_arrival < 0:
                full_recharge(vehicle, current_state.battery_arrival)
                current_state.battery_arrival = 0
                current_state.battery_departure = 0
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {}
    }