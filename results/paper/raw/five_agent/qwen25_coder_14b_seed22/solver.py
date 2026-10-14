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
        return sum(distance(instance.node_map[route[i]], instance.node_map[route[i+1]]) for i in range(len(route) - 1))
    
    # Function to check if a route is feasible
    def is_feasible(route):
        stops = propagate_route(instance, route)
        for stop in stops:
            if stop.battery_departure < 0:
                return False
        return True
    
    # Function to find the nearest unvisited customer to a node
    def nearest_unvisited(node_id):
        nearest = None
        min_distance = float('inf')
        for customer_id in unvisited_customers:
            d = distance(instance.node_map[node_id], instance.node_map[customer_id])
            if d < min_distance:
                min_distance = d
                nearest = customer_id
        return nearest
    
    # Function to find the nearest charging station to a node
    def nearest_charging_station(node_id):
        nearest = None
        min_distance = float('inf')
        for station_id in instance.station_ids:
            d = distance(instance.node_map[node_id], instance.node_map[station_id])
            if d < min_distance:
                min_distance = d
                nearest = station_id
        return nearest
    
    # Main loop to build routes
    while unvisited_customers:
        # Select a random route to extend
        route = random.choice(routes)
        
        # Find the nearest unvisited customer to the last node in the route
        next_customer = nearest_unvisited(route[-1])
        
        # Insert the next customer into the route
        route.append(next_customer)
        unvisited_customers.remove(next_customer)
        
        # Check if the route is still feasible
        if not is_feasible(route):
            # If not feasible, remove the last customer and try again
            route.pop()
            unvisited_customers.append(next_customer)
            
            # Find the nearest charging station to the last node in the route
            charging_station = nearest_charging_station(route[-1])
            
            # Insert the charging station into the route
            route.append(charging_station)
            
            # Check if the route is still feasible after adding the charging station
            if not is_feasible(route):
                # If not feasible, remove the last customer and charging station and try again
                route.pop()
                route.pop()
                unvisited_customers.append(next_customer)
    
    # Add the depot at the end of each route
    for route in routes:
        route.append(instance.depot_id)
    
    return {"routes": routes, "metadata": {}}

