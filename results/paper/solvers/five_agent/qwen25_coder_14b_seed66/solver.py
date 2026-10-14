import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with just the depot
    routes = [[instance.depot_id]]
    
    # List of all customers to be visited
    unvisited_customers = list(instance.customer_ids)
    
    # Function to calculate the total distance of a route
    def total_distance(route):
        return sum(distance(instance.node_map[route[i]], instance.node_map[route[i+1]]) for i in range(len(route) - 1))
    
    # Function to insert a customer into a route
    def insert_customer(route, customer_id):
        best_distance = float('inf')
        best_position = -1
        customer_node = instance.node_map[customer_id]
        
        for i in range(1, len(route)):
            current_distance = total_distance(route)
            new_route = route[:i] + [customer_id] + route[i:]
            new_distance = total_distance(new_route)
            
            if new_distance < best_distance:
                best_distance = new_distance
                best_position = i
        
        return route[:best_position] + [customer_id] + route[best_position:]
    
    # Function to check if a route respects capacity constraints
    def is_capacity_respected(route):
        stops = propagate_route(instance, route)
        for stop in stops:
            if stop.load > instance.vehicle.capacity:
                return False
        return True
    
    # Function to insert charging stations if necessary
    def insert_charge(route):
        vehicle = instance.vehicle
        stops = propagate_route(instance, route)
        
        for i in range(len(stops) - 1):
            if stops[i].battery_departure < stops[i+1].battery_arrival:
                # Insert a charging station
                for station_id in instance.station_ids:
                    station_node = instance.node_map[station_id]
                    if energy_required(station_node, instance.node_map[route[i+1]], instance.vehicle) <= instance.vehicle.battery_capacity:
                        route.insert(i + 1, station_id)
                        stops = propagate_route(instance, route)
                        break
                i -= 1  # Re-evaluate the previous stop after insertion
    
    # Main loop to build routes
    while unvisited_customers:
        customer_id = random.choice(unvisited_customers)
        unvisited_customers.remove(customer_id)
        
        # Try to insert the customer into an existing route
        inserted = False
        for i, route in enumerate(routes):
            if is_capacity_respected(route + [customer_id]):
                routes[i] = insert_customer(route, customer_id)
                insert_charge(routes[i])  # Insert charging stations after inserting the customer
                inserted = True
                break
        
        # If no existing route can accommodate the customer, create a new route
        if not inserted:
            new_route = [instance.depot_id, customer_id, instance.depot_id]
            insert_charge(new_route)  # Insert charging stations for the new route
            routes.append(new_route)
    
    # Ensure all routes start and end at the depot
    for i in range(len(routes)):
        if routes[i][0] != instance.depot_id:
            routes[i] = [instance.depot_id] + routes[i]
        if routes[i][-1] != instance.depot_id:
            routes[i].append(instance.depot_id)
    
    # Check and adjust routes to ensure sufficient battery for return trips
    for route in routes:
        stops = propagate_route(instance, route)
        if stops[-1].battery_departure < 0:
            # Insert a charging station before the last customer to ensure sufficient battery for return
            for station_id in instance.station_ids:
                station_node = instance.node_map[station_id]
                if energy_required(station_node, instance.node_map[route[-2]], instance.vehicle) <= instance.vehicle.battery_capacity:
                    route.insert(-1, station_id)
                    break
    
    return {"routes": routes, "metadata": {}}


