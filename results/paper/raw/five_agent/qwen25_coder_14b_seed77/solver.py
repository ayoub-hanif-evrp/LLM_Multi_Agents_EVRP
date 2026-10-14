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
        dist = 0
        for i in range(len(route) - 1):
            dist += distance(instance.node_map[route[i]], instance.node_map[route[i + 1]])
        return dist
    
    # Helper function to check if a route is feasible
    def is_feasible(route):
        stops = propagate_route(instance, route)
        for stop in stops:
            if stop.battery_departure < 0:
                return False
        return True
    
    # Helper function to insert a customer into a route
    def insert_customer(route, customer_id):
        best_distance = float('inf')
        best_position = -1
        
        for i in range(len(route) - 1):
            route.insert(i + 1, customer_id)
            if is_feasible(route):
                dist = total_distance(route)
                if dist < best_distance:
                    best_distance = dist
                    best_position = i + 1
            route.pop(i + 1)
        
        if best_position != -1:
            route.insert(best_position, customer_id)
            return True
        return False
    
    # Main loop to build routes
    while unvisited_customers:
        # Select a random unvisited customer
        customer_id = random.choice(unvisited_customers)
        customer = instance.node_map[customer_id]
        
        # Find the best route to insert the customer
        best_route = None
        best_distance = float('inf')
        
        for route in routes:
            if insert_customer(route, customer_id):
                dist = total_distance(route)
                if dist < best_distance:
                    best_distance = dist
                    best_route = route
        
        # If a feasible route was found, add the customer to it
        if best_route:
            unvisited_customers.remove(customer_id)
        else:
            # If no feasible route was found, create a new route
            routes.append([instance.depot_id, customer_id])
            unvisited_customers.remove(customer_id)
    
    # Add the depot to the end of each route
    for route in routes:
        route.append(instance.depot_id)
    
    return {"routes": routes, "metadata": {}}

