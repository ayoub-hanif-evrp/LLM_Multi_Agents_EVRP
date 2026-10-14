from evrptw_autolab.problem.types import EVRPTWInstance
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes
    routes = [[] for _ in range(instance.n_customers)]
    
    # Helper function to insert a charge station into a route
    def insert_charge(route, station_id):
        for i in range(len(route) - 1):
            if energy_required(instance.node_map[route[i]], instance.node_map[route[i + 1]], instance.vehicle) > instance.vehicle.battery_capacity:
                routes[routes.index(route)].insert(i + 1, station_id)
                return True
        return False
    
    # Helper function to calculate the total distance of a route
    def total_distance(route):
        return sum(distance(instance.node_map[route[i]], instance.node_map[route[i + 1]]) for i in range(len(route) - 1))
    
    # Assign customers to routes
    for customer in instance.customers:
        assigned = False
        for route in routes:
            if not assigned:
                route.append(customer.id)
                if insert_charge(route, random.choice(instance.station_ids)):
                    assigned = True
        if not assigned:
            routes[0].append(customer.id)
            if insert_charge(routes[0], random.choice(instance.station_ids)):
                assigned = True
    
    # Ensure routes start and end at the depot
    for route in routes:
        route.insert(0, instance.depot_id)
        route.append(instance.depot_id)
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {
            "total_distance": sum(total_distance(route) for route in routes),
            "number_of_vehicles": len(routes)
        }
    }