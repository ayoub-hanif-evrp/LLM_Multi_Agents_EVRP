import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes
    routes = [[] for _ in range(instance.vehicle.capacity)]
    
    # Function to add a customer to a route
    def add_customer_to_route(route, customer_id):
        route.append(customer_id)
    
    # Function to calculate the total distance of a route
    def total_distance(route):
        total = 0
        for i in range(len(route) - 1):
            total += distance(instance.node_map[route[i]], instance.node_map[route[i + 1]])
        return total
    
    # Main optimization loop
    start_time = time.time()
    while time.time() - start_time < time_limit_s:
        for route in routes:
            if route:
                last_customer = route[-1]
                for customer_id in instance.customer_ids:
                    if customer_id not in route:
                        if energy_required(instance.node_map[last_customer], instance.node_map[customer_id], instance.vehicle) <= instance.vehicle.battery_capacity:
                            add_customer_to_route(route, customer_id)
                            break
    
    # Ensure all customers are visited
    remaining_customers = set(instance.customer_ids)
    for route in routes:
        remaining_customers -= set(route)
    
    # Add remaining customers to new routes
    for customer_id in remaining_customers:
        for route in routes:
            if not route:
                add_customer_to_route(route, customer_id)
                break
    
    # Add depot to the start and end of each route
    for i in range(len(routes)):
        if routes[i]:
            routes[i].insert(0, instance.depot_id)
            routes[i].append(instance.depot_id)
    
    # Calculate metadata
    metadata = {
        "total_distance": sum(total_distance(route) for route in routes),
        "number_of_vehicles": len(routes)
    }
    
    return {"routes": routes, "metadata": metadata}