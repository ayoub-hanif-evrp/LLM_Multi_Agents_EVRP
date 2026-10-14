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
            if stop.battery_departure < 0 or stop.load > instance.vehicle.capacity:
                return False
        return True
    
    # Function to insert a charging station if needed
    def insert_charge(route):
        stops = propagate_route(instance, route)
        for i in range(len(stops) - 1):
            if stops[i].battery_departure < 0:
                # Insert a charging station before the node that causes the battery to go negative
                route.insert(i + 1, random.choice(instance.station_ids))
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
            # Try inserting the customer at every possible position
            for i in range(1, len(route)):
                new_route = route[:i] + [customer_id] + route[i:]
                new_route = insert_charge(new_route)
                
                if is_valid_route(new_route):
                    new_distance = total_distance(new_route)
                    if new_distance < best_distance:
                        best_distance = new_distance
                        best_route = new_route
        
        # If no valid route was found, create a new route
        if not best_route:
            best_route = [instance.depot_id, customer_id, instance.depot_id]
            best_route = insert_charge(best_route)
        
        # Add the best route to the list of routes
        routes.append(best_route)
    
    # Ensure all routes start and end at the depot
    for route in routes:
        if route[0] != instance.depot_id:
            route.insert(0, instance.depot_id)
        if route[-1] != instance.depot_id:
            route.append(instance.depot_id)
    
    return {"routes": routes, "metadata": {}}

