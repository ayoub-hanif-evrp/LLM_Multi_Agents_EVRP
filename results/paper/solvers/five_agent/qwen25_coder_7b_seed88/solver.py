import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    routes = []
    metadata = {
        "number_of_vehicles": 0,
        "total_distance": 0.0
    }

    # Initialize a list to keep track of visited customers
    visited_customers = set()

    # Iterate over each customer and assign them to a route
    for customer_id in instance.customer_ids:
        if customer_id not in visited_customers:
            route = [instance.depot_id, customer_id, instance.depot_id]
            routes.append(route)
            visited_customers.add(customer_id)

    return {"routes": routes, "metadata": metadata}

