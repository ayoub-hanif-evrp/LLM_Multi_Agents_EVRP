import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize variables
    depot_id = instance.depot_id
    customer_ids = list(instance.customer_ids)
    station_ids = list(instance.station_ids)
    vehicle = instance.vehicle
    
    # Shuffle customers for randomization
    random.shuffle(customer_ids)
    
    # Create initial routes with depot at the start and end
    routes = [[depot_id] for _ in range(instance.n_customers)]
    
    # Assign each customer to a route
    for customer_id in customer_ids:
        assigned = False
        for route in routes:
            if not assigned:
                # Check if adding the customer to the route is feasible
                route.append(customer_id)
                route.append(depot_id)
                
                # Propagate the route to check feasibility
                stop_states = propagate_route(instance, route)
                
                # Check if the route is feasible
                if all(stop_state.battery_departure >= 0 for stop_state in stop_states):
                    assigned = True
                else:
                    # If not feasible, remove the customer and try the next route
                    route.pop(-1)
                    route.pop(-1)
        # If no route is feasible for the customer, create a new route
        if not assigned:
            routes.append([depot_id, customer_id, depot_id])
    
    # Add charging stations to routes if needed
    for route in routes:
        # Check if the route needs charging
        stop_states = propagate_route(instance, route)
        last_stop = stop_states[-1]
        
        if last_stop.battery_departure < 0:
            # Find a suitable station to add
            for station_id in station_ids:
                route.insert(-1, station_id)
                stop_states = propagate_route(instance, route)
                last_stop = stop_states[-1]
                
                if last_stop.battery_departure >= 0:
                    break
                else:
                    route.pop(-2)
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {
            "seed": seed,
            "time_limit_s": time_limit_s,
            "num_routes": len(routes),
            "total_distance": sum(distance(instance.node_map[route[i]], instance.node_map[route[i+1]]) for route in routes for i in range(len(route)-1))
        }
    }