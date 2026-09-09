import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot as the starting and ending point
    routes = [[instance.depot_id]]
    
    # Assign each customer to a route
    for customer_id in instance.customer_ids:
        # Randomly select a route to add the customer
        route_index = random.randint(0, len(routes) - 1)
        routes[route_index].append(customer_id)
        routes[route_index].append(instance.depot_id)
    
    return {"routes": routes, "metadata": {}}