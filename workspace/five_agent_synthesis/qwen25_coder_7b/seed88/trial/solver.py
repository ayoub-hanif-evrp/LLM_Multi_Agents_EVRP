import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes
    routes = [[] for _ in range(instance.vehicle.capacity)]
    depot_id = instance.depot_id
    customers = list(instance.customer_ids)
    
    # Function to calculate the total distance of a route
    def total_distance(route):
        return sum(distance(instance.node_map[route[i]], instance.node_map[route[i+1]]) for i in range(len(route)-1))
    
    # Main loop to construct routes
    while customers:
        route = [depot_id]
        current_capacity = instance.vehicle.capacity
        current_battery = instance.vehicle.battery_capacity
        
        while customers and current_capacity > 0 and current_battery > 0:
            next_customer = None
            min_distance = float('inf')
            
            for customer in customers:
                dist = distance(instance.node_map[route[-1]], instance.node_map[customer])
                if dist < min_distance:
                    min_distance = dist
                    next_customer = customer
            
            if next_customer is None:
                break
            
            route.append(next_customer)
            current_capacity -= 1
            current_battery -= energy_required(instance.node_map[route[-2]], instance.node_map[route[-1]], instance.vehicle)
            customers.remove(next_customer)
        
        route.append(depot_id)
        routes[0].extend(route)
    
    # Remove empty routes
    routes = [route for route in routes if route]
    
    return {
        "routes": routes,
        "metadata": {
            "total_distance": sum(total_distance(route) for route in routes)
        }
    }