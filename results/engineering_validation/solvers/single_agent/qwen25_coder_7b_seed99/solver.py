from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    vehicle = instance.vehicle
    
    # Initialize routes
    routes = [[depot_id]]
    
    # Assign customers to routes
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        for route in routes:
            if len(route) == 1:
                route.append(customer_id)
                break
            else:
                previous_node = instance.node_map[route[-1]]
                next_node = instance.node_map[route[0]]
                if distance(previous_node, customer) + distance(customer, next_node) < distance(previous_node, next_node):
                    route.insert(-1, customer_id)
                    break
        else:
            routes.append([depot_id, customer_id, depot_id])
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {}
    }