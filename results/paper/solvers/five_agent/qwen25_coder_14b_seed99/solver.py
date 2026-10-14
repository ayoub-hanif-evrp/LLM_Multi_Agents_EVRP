import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id]]
    
    # List of all customers to be visited
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
    
    # Function to insert a customer into a route
    def insert_customer(route, customer_id):
        best_route = None
        best_distance = float('inf')
        customer_node = instance.node_map[customer_id]
        
        for i in range(1, len(route)):
            new_route = route[:i] + [customer_id] + route[i:]
            if is_feasible(new_route):
                new_distance = total_distance(new_route)
                if new_distance < best_distance:
                    best_distance = new_distance
                    best_route = new_route
        
        return best_route
    
    # Function to insert charging stations into a route
    def insert_charge(route):
        stops = propagate_route(instance, route)
        new_route = route[:]
        
        for i in range(1, len(stops) - 1):
            if stops[i].battery_departure < instance.vehicle.start_soc:
                station_id = random.choice(instance.station_ids)
                new_route.insert(i, station_id)
        
        return new_route
    
    # Main routing logic
    while unvisited_customers:
        customer_id = random.choice(unvisited_customers)
        unvisited_customers.remove(customer_id)
        
        best_route = None
        best_distance = float('inf')
        
        for route in routes:
            new_route = insert_customer(route, customer_id)
            if new_route:
                new_route = insert_charge(new_route)
                new_distance = total_distance(new_route)
                if new_distance < best_distance:
                    best_distance = new_distance
                    best_route = new_route
        
        if best_route:
            routes.append(best_route)
        else:
            # If no feasible route is found, create a new route starting from the depot
            routes.append([instance.depot_id, customer_id, instance.depot_id])
    
    # Ensure each route starts and ends at the depot
    for i in range(len(routes)):
        if routes[i][0] != instance.depot_id:
            routes[i] = [instance.depot_id] + routes[i]
        if routes[i][-1] != instance.depot_id:
            routes[i] = routes[i] + [instance.depot_id]
    
    return {"routes": routes, "metadata": {}}

