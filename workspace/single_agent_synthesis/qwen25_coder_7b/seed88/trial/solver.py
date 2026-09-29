from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    vehicle = instance.vehicle
    
    # Initialize routes with the depot
    routes = [[depot_id] for _ in range(len(customer_ids))]
    
    # Assign customers to routes
    for customer in customers:
        # Find the route with the least load
        min_load_route = min(routes, key=lambda route: sum(1 for c in instance.customers if c.id in route))
        min_load_route.append(customer.id)
        min_load_route.append(depot_id)
    
    # Check for charging feasibility
    for route in routes:
        state = propagate_route(instance, route)
        for i in range(len(state) - 1):
            if state[i].battery_arrival < 0:
                # Find a charging station
                for station in instance.stations:
                    new_route = route[:i+1] + [station.id] + route[i+1:]
                    new_state = propagate_route(instance, new_route)
                    if new_state[-1].battery_arrival >= 0:
                        route = new_route
                        break
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {}
    }