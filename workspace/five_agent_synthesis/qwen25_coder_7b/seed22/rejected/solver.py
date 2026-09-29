import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes
    routes = [[] for _ in range(instance.vehicle.capacity)]
    depot_id = instance.depot_id
    customers = list(instance.customer_ids)
    
    # Function to add a customer to a route
    def add_customer_to_route(route, customer_id):
        route.append(customer_id)
    
    # Function to calculate the total distance of a route
    def total_distance(route):
        total = 0
        for i in range(len(route) - 1):
            total += distance(instance.node_map[route[i]], instance.node_map[route[i + 1]])
        return total
    
    # Main routing loop
    while customers:
        best_route_index = None
        best_route = None
        best_distance = float('inf')
        
        for i in range(len(routes)):
            if not routes[i]:
                continue
            route = routes[i]
            last_customer_id = route[-1]
            last_customer = instance.node_map[last_customer_id]
            for customer_id in customers:
                customer = instance.node_map[customer_id]
                if travel_time(last_customer, customer, instance.vehicle) <= instance.vehicle.battery_capacity:
                    new_route = route + [customer_id]
                    new_distance = total_distance(new_route)
                    if new_distance < best_distance:
                        best_route_index = i
                        best_route = new_route
                        best_distance = new_distance
        
        if best_route_index is not None:
            routes[best_route_index] = best_route
            customers.remove(best_route[-1])
        else:
            break
    
    # Ensure all customers are visited
    for i in range(len(routes)):
        if not routes[i]:
            routes[i] = [depot_id] + customers + [depot_id]
            customers = []
    
    # Calculate total distance
    total_distance = sum(total_distance(route) for route in routes)
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {
            "total_distance": total_distance
        }
    }