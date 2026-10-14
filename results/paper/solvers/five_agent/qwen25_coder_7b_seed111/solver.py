import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id]]
    
    # Add customers to routes
    for customer_id in instance.customer_ids:
        routes[0].append(customer_id)
    
    # Add the depot at the end of the route
    routes[0].append(instance.depot_id)
    
    return {
        "routes": routes,
        "metadata": {}
    }

def build_routes(instance, vehicle):
    routes = []
    current_route = [instance.depot_id]
    current_load = 0
    current_time = instance.depot.ready_time

    for customer in instance.customers:
        if current_load + customer.demand > vehicle.capacity:
            routes.append(current_route)
            current_route = [instance.depot_id]
            current_load = 0
            current_time = instance.depot.ready_time
        current_route.append(customer.id)
        current_load += customer.demand
        current_time += travel_time(instance.node_map[current_route[-2]], instance.node_map[current_route[-1]], vehicle)

    routes.append(current_route)
    return routes

