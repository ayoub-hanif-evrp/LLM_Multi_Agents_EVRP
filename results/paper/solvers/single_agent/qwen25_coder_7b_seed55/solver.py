import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id]]
    
    # Add each customer to a route
    for customer_id in instance.customer_ids:
        customer = instance.node_map[customer_id]
        for i, route in enumerate(routes):
            if len(route) == 1:
                # Start a new route with the depot
                routes.append([instance.depot_id])
                i += 1
            route = routes[i]
            if len(route) > 1:
                prev_node = instance.node_map[route[-2]]
                next_node = instance.node_map[route[-1]]
                if distance(prev_node, customer) + distance(customer, next_node) <= instance.vehicle.capacity:
                    route.append(customer_id)
                    break
        else:
            # If no route can accommodate the customer, start a new one
            routes.append([instance.depot_id, customer_id, instance.depot_id])
    
    # Remove empty routes
    routes = [route for route in routes if len(route) > 1]
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {}
    }