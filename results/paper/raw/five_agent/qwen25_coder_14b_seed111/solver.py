import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id]]
    
    # List of unvisited customers
    unvisited_customers = list(instance.customer_ids)
    
    # Helper function to calculate the total distance of a route
    def total_distance(route):
        total = 0
        for i in range(len(route) - 1):
            total += distance(instance.node_map[route[i]], instance.node_map[route[i + 1]])
        return total
    
    # Helper function to insert a customer into a route
    def insert_customer(route, customer_id):
        best_distance = float('inf')
        best_position = -1
        customer_node = instance.node_map[customer_id]
        
        for i in range(len(route)):
            new_route = route[:i] + [customer_id] + route[i:]
            new_distance = total_distance(new_route)
            if new_distance < best_distance:
                best_distance = new_distance
                best_position = i
        
        return route[:best_position] + [customer_id] + route[best_position:]
    
    # Helper function to check if a route exceeds capacity
    def is_route_within_capacity(route):
        current_load = 0
        for node_id in route:
            node = instance.node_map[node_id]
            current_load += node.demand
            if current_load > instance.vehicle.capacity:
                return False
        return True
    
    # Main loop to build routes
    while unvisited_customers:
        # Select a random unvisited customer
        customer_id = random.choice(unvisited_customers)
        unvisited_customers.remove(customer_id)
        
        # Find the best route to insert the customer
        best_route = None
        best_distance = float('inf')
        
        for route in routes:
            if is_route_within_capacity(route):
                new_route = insert_customer(route, customer_id)
                new_distance = total_distance(new_route)
                if new_distance < best_distance:
                    best_distance = new_distance
                    best_route = new_route
        
        # Add the customer to the best route
        if best_route:
            routes.append(best_route)
        else:
            # If no valid route is found, start a new route
            routes.append([instance.depot_id, customer_id, instance.depot_id])
    
    # Ensure each route starts and ends at the depot
    for i in range(len(routes)):
        if routes[i][0] != instance.depot_id:
            routes[i] = [instance.depot_id] + routes[i]
        if routes[i][-1] != instance.depot_id:
            routes[i] = routes[i] + [instance.depot_id]
    
    # Return the solution
    return {"routes": routes, "metadata": {}}

