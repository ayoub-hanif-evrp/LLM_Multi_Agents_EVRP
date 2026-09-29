import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    n_customers = instance.n_customers
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle
    
    # Initialize routes
    routes = [[] for _ in range(n_customers)]
    
    # Function to calculate the total distance of a route
    def total_distance(route):
        total = 0
        for i in range(len(route) - 1):
            total += distance(instance.node_map[route[i]], instance.node_map[route[i + 1]])
        return total
    
    # Function to calculate the total energy consumption of a route
    def total_energy_consumption(route):
        total = 0
        current_soc = vehicle.start_soc
        for i in range(len(route) - 1):
            energy = energy_required(instance.node_map[route[i]], instance.node_map[route[i + 1]], vehicle)
            current_soc -= energy / vehicle.battery_capacity * vehicle.consumption_rate
            total += energy
        return total
    
    # Function to check if a route is feasible
    def is_feasible(route):
        current_soc = vehicle.start_soc
        for i in range(len(route) - 1):
            energy = energy_required(instance.node_map[route[i]], instance.node_map[route[i + 1]], vehicle)
            current_soc -= energy / vehicle.battery_capacity * vehicle.consumption_rate
            if current_soc < 0:
                return False
        return True
    
    # Main loop to construct routes
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        best_route = None
        best_distance = float('inf')
        best_energy = float('inf')
        
        for route in routes:
            if is_feasible(route + [customer_id]):
                route.append(customer_id)
                if total_distance(route) < best_distance or (total_distance(route) == best_distance and total_energy_consumption(route) < best_energy):
                    best_route = route
                    best_distance = total_distance(route)
                    best_energy = total_energy_consumption(route)
                route.pop()
        
        if best_route:
            routes[routes.index(best_route)].append(customer_id)
    
    # Convert routes to the required format
    result_routes = []
    for route in routes:
        if route:
            result_routes.append([depot_id] + route + [depot_id])
    
    return {"routes": result_routes, "metadata": {}}