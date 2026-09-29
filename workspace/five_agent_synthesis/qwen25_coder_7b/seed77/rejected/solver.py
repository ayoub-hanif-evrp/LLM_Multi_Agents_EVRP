import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes
    routes = [[] for _ in range(instance.vehicle.capacity)]
    depot_id = instance.depot_id
    
    # Function to calculate the total distance of a route
    def total_distance(route):
        return sum(distance(instance.node_map[route[i]], instance.node_map[route[i + 1]]) for i in range(len(route) - 1))
    
    # Function to calculate the total energy consumption of a route
    def total_energy(route):
        return sum(energy_required(instance.node_map[route[i]], instance.node_map[route[i + 1]], instance.vehicle) for i in range(len(route) - 1))
    
    # Function to check if a route is feasible
    def is_feasible(route):
        current_battery = instance.vehicle.battery_capacity
        for i in range(len(route) - 1):
            current_distance = distance(instance.node_map[route[i]], instance.node_map[route[i + 1]])
            current_energy = energy_required(instance.node_map[route[i]], instance.node_map[route[i + 1]], instance.vehicle)
            if current_battery < current_energy:
                return False
            current_battery -= current_energy
        return True
    
    # Main optimization loop
    start_time = time.time()
    while time.time() - start_time < time_limit_s:
        for route in routes:
            if route:
                # Randomly select a customer to move
                customer_id = random.choice(route[1:-1])
                index = route.index(customer_id)
                # Try to insert the customer at a different position
                for i in range(len(route)):
                    if i != index:
                        new_route = route[:i] + [customer_id] + route[i:index] + route[index + 1:]
                        if is_feasible(new_route):
                            route = new_route
                            break
        # Check if the solution is feasible
        if all(is_feasible(route) for route in routes):
            break
    
    # Return the solution
    return {"routes": routes, "metadata": {"total_distance": sum(total_distance(route) for route in routes), "total_energy": sum(total_energy(route) for route in routes)}}