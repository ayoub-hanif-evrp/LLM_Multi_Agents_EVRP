import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    import random
    from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
    
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
    
    # Helper function to insert a charging station if needed
    def insert_charges(route):
        vehicle = instance.vehicle
        stops = propagate_route(instance, route)
        for i in range(len(stops) - 1):
            if stops[i].battery_departure < vehicle.start_soc:
                # Insert a charging station before the next node
                route.insert(i + 1, random.choice(instance.station_ids))
                break
        return route
    
    # Helper function to check if a route is feasible
    def is_feasible(route):
        stops = propagate_route(instance, route)
        for stop in stops:
            if stop.arrival_time < instance.node_map[stop.node_id].ready_time:
                return False
            if stop.arrival_time > instance.node_map[stop.node_id].due_time:
                return False
            if stop.load > instance.vehicle.capacity:
                return False
            if stop.battery_departure < instance.vehicle.start_soc:
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
            # Try inserting the customer at the end of the route
            route.append(customer_id)
            route = insert_charges(route)
            if is_feasible(route):
                current_distance = total_distance(route)
                if current_distance < best_distance:
                    best_distance = current_distance
                    best_route = route
            route.pop()  # Remove the customer to try the next route
        
        # If no valid route was found, create a new one
        if not best_route:
            best_route = [instance.depot_id, customer_id, instance.depot_id]
            best_route = insert_charges(best_route)
        
        # Add the best route to the list of routes
        routes.append(best_route)
    
    # Ensure all routes start and end at the depot
    for route in routes:
        if route[0] != instance.depot_id:
            route.insert(0, instance.depot_id)
        if route[-1] != instance.depot_id:
            route.append(instance.depot_id)
    
    return {"routes": routes, "metadata": {}}


