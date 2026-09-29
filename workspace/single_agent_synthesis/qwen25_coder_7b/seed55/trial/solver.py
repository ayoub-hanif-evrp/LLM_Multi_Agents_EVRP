from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    depot = instance.depot
    vehicle = instance.vehicle
    
    # Initialize routes
    routes = [[depot_id]]
    
    # Add customers to routes
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        # Find the route with the least distance to the customer
        min_distance = float('inf')
        best_route_index = 0
        for i, route in enumerate(routes):
            if route[-1] == depot_id:
                last_node = depot
            else:
                last_node = instance.node_map[route[-1]]
            dist = distance(last_node, customer)
            if dist < min_distance:
                min_distance = dist
                best_route_index = i
        routes[best_route_index].append(customer_id)
        routes[best_route_index].append(depot_id)
    
    # Check feasibility
    for route in routes:
        if route[0] != depot_id or route[-1] != depot_id:
            raise ValueError("Each route must start and end at the depot.")
    
    # Apply charging logic
    for route_index, route in enumerate(routes):
        if route_index == 0:
            continue  # Skip the depot route
        for i in range(1, len(route) - 1):
            node_id = route[i]
            node = instance.node_map[node_id]
            if node.kind == "station":
                state = propagate_route(instance, route[:i + 1])[-1]
                battery_on_arrival = state.battery_departure
                recharge_decision = full_recharge(vehicle, battery_on_arrival)
                if recharge_decision.energy_charged < 0:
                    # Handle battery undercharge by skipping the station
                    continue
                state.battery_departure = recharge_decision.battery_departure
                state.energy_charged = recharge_decision.energy_charged
    
    # Return the solution
    return {"routes": routes, "metadata": {}}