from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes and depot
    depot_id = instance.depot_id
    customer_ids = list(instance.customer_ids)
    station_ids = list(instance.station_ids)
    routes = []
    
    # Helper function to calculate the total energy required for a route
    def total_energy_required(route):
        total_energy = 0
        vehicle = instance.vehicle
        for i in range(len(route) - 1):
            total_energy += energy_required(instance.node_map[route[i]], instance.node_map[route[i + 1]], vehicle)
        return total_energy
    
    # Helper function to calculate the total travel time for a route
    def total_travel_time(route):
        total_time = 0
        vehicle = instance.vehicle
        for i in range(len(route) - 1):
            total_time += travel_time(instance.node_map[route[i]], instance.node_map[route[i + 1]], vehicle)
        return total_time
    
    # Main loop to construct routes
    while customer_ids:
        current_route = [depot_id]
        remaining_customers = customer_ids[:]
        random.shuffle(remaining_customers)
        
        for customer_id in remaining_customers:
            if customer_id not in current_route:
                current_route.append(customer_id)
                customer_ids.remove(customer_id)
        
        current_route.append(depot_id)
        routes.append(current_route)
    
    # Return the constructed routes
    return {
        "routes": routes,
        "metadata": {
            "total_energy": sum(total_energy_required(route) for route in routes),
            "total_travel_time": sum(total_travel_time(route) for route in routes)
        }
    }