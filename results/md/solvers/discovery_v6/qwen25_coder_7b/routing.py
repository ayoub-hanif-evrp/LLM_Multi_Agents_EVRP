import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot as the starting and ending point
    routes = [[instance.depot_id]]
    
    # Assign each customer to a route
    for customer_id in instance.customer_ids:
        assigned = False
        for route in routes:
            if len(route) < instance.vehicle.capacity + 1:  # Ensure there is space for the customer and return trip
                route.append(customer_id)
                assigned = True
                break
        if not assigned:
            routes.append([instance.depot_id, customer_id, instance.depot_id])
    
    # Return the solution with metadata
    return {
        "routes": routes,
        "metadata": {}
    }