import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes
    routes = [[] for _ in range(instance.vehicle.capacity)]
    vehicle_loads = [0] * instance.vehicle.capacity
    
    # Function to add a customer to a route
    def add_customer_to_route(route_index, customer_id):
        route = routes[route_index]
        customer = instance.node_map[customer_id]
        if vehicle_loads[route_index] + customer.load > instance.vehicle.capacity:
            return False
        route.append(customer_id)
        vehicle_loads[route_index] += customer.load
        return True
    
    # Function to calculate the total distance of routes
    def total_distance():
        return sum(distance(instance.node_map[route[0]], instance.node_map[route[-1]]) for route in routes if route)
    
    # Main loop to construct routes
    for customer_id in instance.customer_ids:
        best_route_index = -1
        best_route_distance = float('inf')
        
        for route_index in range(instance.vehicle.capacity):
            if add_customer_to_route(route_index, customer_id):
                route = routes[route_index]
                route_distance = total_distance()
                if route_distance < best_route_distance:
                    best_route_index = route_index
                    best_route_distance = route_distance
                remove_customer_from_route(route_index, customer_id)
        
        if best_route_index != -1:
            add_customer_to_route(best_route_index, customer_id)
    
    # Finalize routes
    for route in routes:
        if route:
            route.append(instance.depot_id)
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {
            "total_distance": total_distance()
        }
    }

def remove_customer_from_route(route_index, customer_id):
    route = routes[route_index]
    customer = instance.node_map[customer_id]
    route.remove(customer_id)
    vehicle_loads[route_index] -= customer.load