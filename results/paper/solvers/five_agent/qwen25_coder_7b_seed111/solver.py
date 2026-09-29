import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes
    routes = [[] for _ in range(instance.n_customers)]
    depot_id = instance.depot_id
    customers = instance.customer_ids
    
    # Assign customers to routes
    for customer in customers:
        # Find the nearest station
        nearest_station = min(instance.station_ids, key=lambda station: distance(instance.node_map[customer], instance.node_map[station]))
        # Add customer to the route that has the least distance to the nearest station
        min_distance = float('inf')
        min_route_index = -1
        for i, route in enumerate(routes):
            if route:
                last_node = route[-1]
                dist = distance(instance.node_map[last_node], instance.node_map[nearest_station]) + distance(instance.node_map[nearest_station], instance.node_map[customer])
                if dist < min_distance:
                    min_distance = dist
                    min_route_index = i
        routes[min_route_index].append(customer)
    
    # Add depot to the start and end of each route
    for i, route in enumerate(routes):
        routes[i] = [depot_id] + route + [depot_id]
    
    # Return the solution
    return {"routes": routes, "metadata": {}}