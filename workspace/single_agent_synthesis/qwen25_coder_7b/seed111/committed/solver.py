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
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {}
    }