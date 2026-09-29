from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle
    
    # Initialize routes
    routes = [[depot_id]]
    
    # Add customers to routes
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        for route in routes:
            if len(route) == 1:
                route.append(customer_id)
                break
            else:
                last_node_id = route[-1]
                last_node = instance.node_map[last_node_id]
                if last_node.kind == 'customer' and last_node.due_time > customer.ready_time:
                    route.append(customer_id)
                    break
    
    # Add depot to routes
    for route in routes:
        route.append(depot_id)
    
    # Apply charging to routes
    for i, route in enumerate(routes):
        route_states = propagate_route(instance, route)
        for j in range(len(route_states) - 1):
            current_state = route_states[j]
            next_state = route_states[j + 1]
            if next_state.node_id in instance.station_ids:
                recharge_decision = full_recharge(vehicle, current_state.battery_arrival)
                next_state.energy_charged = recharge_decision.energy_charged
                next_state.battery_departure = recharge_decision.battery_departure
                next_state.distance_so_far += recharge_decision.duration
                # Ensure battery_departure is non-negative
                if next_state.battery_departure < 0:
                    next_state.battery_departure = 0
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {}
    }