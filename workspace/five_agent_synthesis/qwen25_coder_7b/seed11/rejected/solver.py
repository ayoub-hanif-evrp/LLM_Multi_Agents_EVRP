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
        return sum(distance(instance.node_map[route[i]], instance.node_map[route[i + 1]]) for i in range(len(route) - 1))
    
    # Function to calculate the total energy consumption of a route
    def total_energy_consumption(route):
        total_energy = 0
        current_battery = vehicle.start_soc
        for i in range(len(route) - 1):
            current_battery -= energy_required(instance.node_map[route[i]], instance.node_map[route[i + 1]], vehicle)
            total_energy += energy_required(instance.node_map[route[i]], instance.node_map[route[i + 1]], vehicle)
        return total_energy
    
    # Main optimization loop
    for _ in range(100):  # Number of iterations
        for i in range(n_customers):
            if customer_ids[i] not in [route[0] for route in routes]:
                # Select a random customer to add to a route
                customer = random.choice(customer_ids)
                customer_id = instance.node_map[customer].id
                
                # Find the best route to add the customer to
                best_route = None
                best_distance = float('inf')
                best_energy = float('inf')
                
                for route in routes:
                    if customer_id not in route:
                        new_route = route + [customer_id]
                        new_distance = total_distance(new_route)
                        new_energy = total_energy_consumption(new_route)
                        if new_distance < best_distance or (new_distance == best_distance and new_energy < best_energy):
                            best_route = new_route
                            best_distance = new_distance
                            best_energy = new_energy
                
                if best_route:
                    routes[routes.index(best_route)].append(customer_id)
    
    # Ensure each customer is visited exactly once
    for route in routes:
        if len(route) == 1:
            route.append(depot_id)
    
    # Return the solution
    return {"routes": routes, "metadata": {"vehicles": len(routes), "distance": sum(total_distance(route) for route in routes)}}