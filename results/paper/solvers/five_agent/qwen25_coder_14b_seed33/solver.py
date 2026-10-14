import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id]]
    
    # List of unvisited customers
    unvisited_customers = list(instance.customer_ids)
    
    # Function to calculate the total distance of a route
    def total_distance(route):
        total = 0
        for i in range(len(route) - 1):
            total += distance(instance.node_map[route[i]], instance.node_map[route[i + 1]])
        return total
    
    # Function to check if a route is valid
    def is_valid_route(route):
        stops = propagate_route(instance, route)
        for stop in stops:
            if stop.battery_departure < 0:
                return False
        return True
    
    # Function to insert a charging station if needed
    def insert_charging_station(route):
        stops = propagate_route(instance, route)
        for stop in stops:
            if stop.battery_departure < 0:
                # Insert a charging station at the first feasible position
                for i in range(len(route) - 1):
                    if instance.node_map[route[i]].kind == 'station':
                        route.insert(i + 1, route[i])
                        break
                return route
        return route
    
    # Main loop to build routes
    while unvisited_customers:
        # Select a random unvisited customer
        customer_id = random.choice(unvisited_customers)
        customer = instance.node_map[customer_id]
        
        # Find the best route to insert the customer
        best_route = None
        best_distance = float('inf')
        
        for route in routes:
            # Try inserting the customer at the end of the route
            route.append(customer_id)
            route = insert_charging_station(route)
            if is_valid_route(route):
                current_distance = total_distance(route)
                if current_distance < best_distance:
                    best_distance = current_distance
                    best_route = route
            route.pop()
            
            # Try inserting the customer at the beginning of the route
            route.insert(0, customer_id)
            route = insert_charging_station(route)
            if is_valid_route(route):
                current_distance = total_distance(route)
                if current_distance < best_distance:
                    best_distance = current_distance
                    best_route = route
            route.pop(0)
        
        # If a valid route was found, insert the customer
        if best_route:
            best_route.append(customer_id)
            unvisited_customers.remove(customer_id)
    
    # Ensure each route starts and ends at the depot
    for route in routes:
        if route[0] != instance.depot_id:
            route.insert(0, instance.depot_id)
        if route[-1] != instance.depot_id:
            route.append(instance.depot_id)
    
    return {"routes": routes, "metadata": {}}

