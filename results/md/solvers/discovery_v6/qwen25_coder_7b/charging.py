import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with a single depot visit for each customer
    routes = [[instance.depot_id] + [customer.id] + [instance.depot_id] for customer in instance.customers]
    
    # Example charging policy: full recharge at the depot
    def charge_policy(vehicle, battery_on_arrival):
        return vehicle.battery_capacity
    
    # Evaluate and fix any violations (e.g., capacity, window constraints)
    def fix_violations(routes):
        for route_index, route in enumerate(routes):
            current_load = 0
            for i in range(1, len(route) - 1):
                customer_id = route[i]
                customer = instance.node_map[customer_id]
                travel_time_to_customer = travel_time(instance.node_map[route[i-1]], customer, instance.vehicle)
                travel_time_from_customer = travel_time(customer, instance.node_map[route[(i+1)%len(route)]], instance.vehicle)
                
                if current_load + customer.load > instance.vehicle.capacity:
                    # Split the route at this customer
                    new_route = route[:i+1]
                    routes[route_index] = new_route
                    routes.insert(route_index + 1, [customer_id] + route[i+1:])
                    break
                
                current_load += customer.load
        
        return routes
    
    # Main optimization loop
    for _ in range(100):  # Example number of iterations
        random.shuffle(routes)
        routes = fix_violations(routes)
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {}
    }