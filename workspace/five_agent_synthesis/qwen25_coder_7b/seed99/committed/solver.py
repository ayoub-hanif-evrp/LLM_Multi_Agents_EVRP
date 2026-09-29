import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = list(instance.customer_ids)
    vehicle = instance.vehicle
    depot = instance.depot
    
    # Initialize routes
    routes = [[] for _ in range(len(customer_ids))]
    route_indices = list(range(len(customer_ids)))
    random.shuffle(route_indices)
    
    # Main loop
    while customer_ids:
        route_index = route_indices.pop(0)
        route = routes[route_index]
        current_node = depot_id
        
        while customer_ids:
            next_node = customer_ids[0]
            if distance(instance.node_map[current_node], instance.node_map[next_node]) <= vehicle.capacity:
                route.append(next_node)
                customer_ids.remove(next_node)
                current_node = next_node
            else:
                break
        
        route.append(depot_id)
    
    # Convert routes to string node ids
    routes = [[depot_id] + [str(node) for node in route] + [depot_id] for route in routes]
    
    # Return solution
    return {
        "routes": routes,
        "metadata": {
            "vehicles": len(routes),
            "distance": sum(distance(instance.node_map[route[i]], instance.node_map[route[i+1]]) for route in routes for i in range(len(route)-1))
        }
    }