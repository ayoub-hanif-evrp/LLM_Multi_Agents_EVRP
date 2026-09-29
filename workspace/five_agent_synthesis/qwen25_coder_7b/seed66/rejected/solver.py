import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes
    routes = [[] for _ in range(instance.vehicle.capacity)]
    depot_id = instance.depot_id
    
    # Function to add a customer to a route
    def add_to_route(route, customer):
        if energy_required(route[-1], customer, instance.vehicle) + customer.battery_capacity <= instance.vehicle.battery_capacity:
            route.append(customer.id)
            return True
        return False
    
    # Function to calculate the total distance of a route
    def route_distance(route):
        return sum(distance(instance.node_map[route[i]], instance.node_map[route[i+1]]) for i in range(len(route)-1))
    
    # Function to calculate the total distance of all routes
    def total_distance(routes):
        return sum(route_distance(route) for route in routes)
    
    # Main optimization loop
    while True:
        # Randomly select a customer and a route
        customer = random.choice(instance.customers)
        route_index = random.randint(0, len(routes)-1)
        
        # Try to add the customer to the selected route
        if add_to_route(routes[route_index], customer):
            continue
        
        # If the customer cannot be added, find a better route
        best_route_index = None
        best_distance = float('inf')
        for i in range(len(routes)):
            if add_to_route(routes[i], customer):
                if route_distance(routes[i]) < best_distance:
                    best_route_index = i
                    best_distance = route_distance(routes[i])
        
        if best_route_index is not None:
            routes[best_route_index].append(customer.id)
        else:
            # If no route can accommodate the customer, create a new route
            routes.append([depot_id, customer.id, depot_id])
    
    # Return the final routes
    return {"routes": routes, "metadata": {"total_distance": total_distance(routes)}}