from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id]]
    
    # Iterate over each customer and assign them to a route
    for customer_id in instance.customer_ids:
        customer = instance.node_map[customer_id]
        best_route_index = -1
        best_route_cost = float('inf')
        
        for i, route in enumerate(routes):
            if len(route) == 1:
                # Check if the customer can be added to the route without violating capacity or time window
                if len(route) + 1 <= instance.vehicle.capacity and customer.due_time >= travel_time(instance.node_map[route[-1]], customer, instance.vehicle):
                    cost = travel_time(instance.node_map[route[-1]], customer, instance.vehicle)
                    if cost < best_route_cost:
                        best_route_index = i
                        best_route_cost = cost
        
        if best_route_index == -1:
            # If no route can be found, create a new route
            routes.append([instance.depot_id, customer_id, instance.depot_id])
        else:
            # Add the customer to the best route
            routes[best_route_index].insert(-1, customer_id)
    
    # Return the routes
    return {"routes": routes, "metadata": {}}