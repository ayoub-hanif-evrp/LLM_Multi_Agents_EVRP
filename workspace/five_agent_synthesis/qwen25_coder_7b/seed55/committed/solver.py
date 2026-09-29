from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    n_customers = instance.n_customers
    customers = instance.customers
    vehicle = instance.vehicle
    
    # Initialize routes
    routes = [[] for _ in range(n_customers)]
    
    # Function to calculate the total distance of a route
    def total_distance(route):
        if not route:
            return 0
        return sum(distance(instance.node_map[route[i]], instance.node_map[route[i + 1]]) for i in range(len(route) - 1))
    
    # Function to check if a route is feasible
    def is_feasible(route):
        if not route:
            return False
        current_load = 0
        current_battery = vehicle.start_soc
        for i in range(len(route) - 1):
            current_node = instance.node_map[route[i]]
            next_node = instance.node_map[route[i + 1]]
            current_load += current_node.demand
            if current_load > vehicle.capacity:
                return False
            travel_dist = distance(current_node, next_node)
            travel_time_ = travel_time(current_node, next_node, vehicle)
            energy_needed = energy_required(current_node, next_node, vehicle)
            if current_battery < energy_needed:
                return False
            current_battery -= energy_needed
            current_battery = max(0, current_battery)
        return True
    
    # Main routing loop
    for customer_id in customer_ids:
        customer = next(c for c in customers if c.id == customer_id)
        if customer.ready_time > 0 or customer.due_time < travel_time(instance.depot, customer, vehicle):
            continue
        for i in range(n_customers):
            if not routes[i]:
                routes[i].append(depot_id)
                routes[i].append(customer_id)
                routes[i].append(depot_id)
                break
    
    # Filter out infeasible routes
    routes = [route for route in routes if is_feasible(route)]
    
    # Calculate the total distance of all routes
    total_distance_ = sum(total_distance(route) for route in routes)
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {
            "total_distance": total_distance_,
            "number_of_vehicles": len(routes)
        }
    }