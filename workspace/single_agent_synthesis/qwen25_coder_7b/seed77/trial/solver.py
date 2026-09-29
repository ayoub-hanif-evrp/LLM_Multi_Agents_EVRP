from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    n_customers = instance.n_customers
    customers = instance.customers
    depot = instance.depot
    vehicle = instance.vehicle
    
    # Initialize routes
    routes = [[depot_id]]
    
    # Visit each customer in a random order
    for customer_id in random.sample(customer_ids, n_customers):
        routes[-1].append(customer_id)
    
    # Add the depot to the end of the route
    routes[-1].append(depot_id)
    
    # Apply full recharge at each station
    for route in routes:
        for i in range(1, len(route) - 1):
            node = instance.node_map[route[i]]
            if node.kind == "station":
                state = propagate_route(instance, route[:i+1])[-1]
                recharge_decision = full_recharge(vehicle, state.battery_arrival)
                state.energy_charged = recharge_decision.energy_charged
                state.battery_departure = recharge_decision.battery_departure
                state.duration += recharge_decision.duration
                route.insert(i + 1, route.pop(i))
    
    return {
        "routes": routes,
        "metadata": {}
    }