import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id]]
    
    # List of customers to visit
    unvisited_customers = list(instance.customer_ids)
    
    # While there are unvisited customers
    while unvisited_customers:
        # Select a random unvisited customer
        customer_id = random.choice(unvisited_customers)
        unvisited_customers.remove(customer_id)
        
        # Find the route with the least distance to the customer
        min_distance = float('inf')
        best_route_index = -1
        
        for i, route in enumerate(routes):
            # Calculate distance from the last node in the route to the customer
            dist = distance(instance.node_map[route[-1]], instance.node_map[customer_id])
            if dist < min_distance:
                min_distance = dist
                best_route_index = i
        
        # Add the customer to the best route
        routes[best_route_index].append(customer_id)
    
    # Add the depot at the end of each route
    for route in routes:
        route.append(instance.depot_id)
    
    # Ensure all routes are valid by adding charging stations if necessary
    for route in routes:
        stops = propagate_route(instance, route)
        current_battery = instance.vehicle.start_soc
        
        for i, stop in enumerate(stops):
            if i > 0:
                current_battery -= energy_required(instance.node_map[route[i-1]], instance.node_map[route[i]], instance.vehicle)
            
            if current_battery < 0:
                # Find the nearest charging station
                min_distance = float('inf')
                nearest_station = None
                for station_id in instance.station_ids:
                    dist = distance(instance.node_map[route[i-1]], instance.node_map[station_id])
                    if dist < min_distance:
                        min_distance = dist
                        nearest_station = station_id
                
                # Insert the charging station into the route
                route.insert(i, nearest_station)
                stops = propagate_route(instance, route)
                current_battery = stops[i+1].battery_departure
    
    # Metadata can be used to store additional information
    metadata = {
        "num_routes": len(routes),
        "total_distance": sum(distance(instance.node_map[r[i]], instance.node_map[r[i+1]]) for r in routes for i in range(len(r)-1))
    }
    
    return {"routes": routes, "metadata": metadata}