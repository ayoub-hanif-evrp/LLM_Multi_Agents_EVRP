import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id]]
    
    # Shuffle customers to create a random order
    customer_ids = list(instance.customer_ids)
    random.shuffle(customer_ids)
    
    # Add customers to routes
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        best_route_index = None
        best_insert_index = None
        best_cost = float('inf')
        
        for i, route in enumerate(routes):
            for j in range(len(route) + 1):
                new_route = route[:j] + [customer_id] + route[j:]
                states = propagate_route(instance, new_route)
                cost = sum(travel_time(instance.node_map[new_route[k]], instance.node_map[new_route[k+1]], instance.vehicle) for k in range(len(new_route) - 1))
                if cost < best_cost:
                    best_cost = cost
                    best_route_index = i
                    best_insert_index = j
        
        if best_route_index is not None:
            routes[best_route_index].insert(best_insert_index, customer_id)
        else:
            routes.append([instance.depot_id, customer_id, instance.depot_id])
    
    # Ensure all customers are visited exactly once
    visited_customers = set()
    for route in routes:
        for node_id in route:
            if node_id.startswith('C'):
                visited_customers.add(node_id)
    
    if len(visited_customers) != instance.n_customers:
        raise ValueError("Not all customers are visited exactly once")
    
    return {
        "routes": routes,
        "metadata": {}
    }