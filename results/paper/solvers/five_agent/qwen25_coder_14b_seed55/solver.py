from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

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
    
    # Function to check if a route is feasible
    def is_feasible(route):
        stops = propagate_route(instance, route)
        for stop in stops:
            if stop.battery_departure < 0:
                return False
        return True
    
    # Function to insert a charging station if needed
    def insert_charge(route):
        stops = propagate_route(instance, route)
        for i in range(len(stops) - 1):
            if stops[i].battery_departure < 0:
                # Insert a charging station before the node that causes the battery to go negative
                route.insert(i + 1, instance.station_ids[0])
                return route
        return route
    
    # Main loop to build routes
    while unvisited_customers:
        # Select a random unvisited customer
        customer_id = random.choice(unvisited_customers)
        unvisited_customers.remove(customer_id)
        
        # Find the best route to insert the customer
        best_route = None
        best_distance = float('inf')
        
        for route in routes:
            # Try inserting the customer at the end of the route
            route.append(customer_id)
            route = insert_charge(route)
            
            if is_feasible(route):
                dist = total_distance(route)
                if dist < best_distance:
                    best_distance = dist
                    best_route = route
            
            # Try inserting the customer at the beginning of the route
            route = [customer_id] + route
            route = insert_charge(route)
            
            if is_feasible(route):
                dist = total_distance(route)
                if dist < best_distance:
                    best_distance = dist
                    best_route = route
            
            # Remove the customer for the next iteration
            route.remove(customer_id)
        
        # If no feasible route was found, create a new route
        if not best_route:
            routes.append([instance.depot_id, customer_id, instance.depot_id])
        else:
            routes.append(best_route)
    
    # Ensure all routes start and end at the depot
    for route in routes:
        if route[0] != instance.depot_id:
            route.insert(0, instance.depot_id)
        if route[-1] != instance.depot_id:
            route.append(instance.depot_id)
    
    return {"routes": routes, "metadata": {}}