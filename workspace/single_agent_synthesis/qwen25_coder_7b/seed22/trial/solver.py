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
                if travel_time(instance.node_map[route[-1]], customer, vehicle) + customer.service_time + travel_time(customer, depot_id, vehicle) <= time_limit_s:
                    route.append(customer_id)
                    break
            else:
                prev_node = instance.node_map[route[-1]]
                next_node = instance.node_map[route[0]]
                if travel_time(prev_node, customer, vehicle) + customer.service_time + travel_time(customer, next_node, vehicle) <= time_limit_s:
                    route.append(customer_id)
                    break
        else:
            routes.append([depot_id, customer_id, depot_id])
    
    # Add depot to end of each route
    for route in routes:
        if route[-1] != depot_id:
            route.append(depot_id)
    
    # Return the solution
    return {"routes": routes, "metadata": {}}