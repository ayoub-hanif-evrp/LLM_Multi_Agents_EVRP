import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    routes = []
    visited_customers = set()
    depot_id = instance.depot_id
    
    while len(visited_customers) < instance.n_customers:
        customer_id = random.choice(list(set(instance.customer_ids) - visited_customers))
        visited_customers.add(customer_id)
        route = [depot_id, customer_id, depot_id]
        routes.append(route)
    
    return {"routes": routes, "metadata": {}}

def build_routes(instance, vehicle):
    routes = []
    visited_customers = set()
    depot_id = instance.depot_id
    current_route = [depot_id]

    while len(visited_customers) < instance.n_customers:
        available_customers = list(set(instance.customer_ids) - visited_customers)
        if not available_customers:
            break

        next_customer = random.choice(available_customers)
        visited_customers.add(next_customer)
        current_route.append(next_customer)

        if len(current_route) > 1 and current_route[-2] != depot_id:
            current_route.append(depot_id)
            routes.append(current_route)
            current_route = [depot_id]

    if current_route and current_route[-1] != depot_id:
        current_route.append(depot_id)
        routes.append(current_route)

    return routes

