import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize variables
    depot_id = instance.depot_id
    customer_ids = list(instance.customer_ids)
    station_ids = list(instance.station_ids)
    vehicle = instance.vehicle
    routes = []
    remaining_customers = set(customer_ids)
    
    # Helper function to calculate the total distance of a route
    def total_distance(route):
        total = 0
        for i in range(len(route) - 1):
            total += distance(instance.node_map[route[i]], instance.node_map[route[i + 1]])
        return total
    
    # Helper function to check if a route is feasible
    def is_feasible(route):
        stops = propagate_route(instance, route)
        for stop in stops:
            if stop.battery_departure < 0:
                return False
        return True
    
    # Helper function to insert a charging station into a route
    def insert_charge(route):
        stops = propagate_route(instance, route)
        for i in range(len(stops) - 1):
            if stops[i].battery_departure < energy_required(instance.node_map[route[i]], instance.node_map[route[i + 1]], vehicle):
                # Insert a charging station
                new_route = route[:i + 1] + [random.choice(station_ids)] + route[i + 1:]
                return insert_charge(new_route)  # Recursively insert charge if needed
        return route
    
    # Main algorithm to build routes
    while remaining_customers:
        # Start a new route from the depot
        current_route = [depot_id]
        current_load = 0
        current_battery = vehicle.start_soc
        
        # Try to add customers to the current route
        while remaining_customers:
            best_customer = None
            best_distance = float('inf')
            best_next_battery = float('-inf')
            
            for customer_id in remaining_customers:
                customer = instance.node_map[customer_id]
                if customer.demand + current_load <= vehicle.capacity:
                    next_battery = current_battery - energy_required(instance.node_map[current_route[-1]], customer, vehicle)
                    if next_battery >= 0:
                        next_distance = distance(instance.node_map[current_route[-1]], customer)
                        if next_distance < best_distance:
                            best_distance = next_distance
                            best_customer = customer_id
                            best_next_battery = next_battery
            
            if best_customer:
                current_route.append(best_customer)
                current_load += instance.node_map[best_customer].demand
                current_battery = best_next_battery
                remaining_customers.remove(best_customer)
            else:
                break
        
        # Add the depot at the end of the route
        current_route.append(depot_id)
        
        # Insert charging stations if necessary
        current_route = insert_charge(current_route)
        
        # Check if the route is feasible
        if is_feasible(current_route):
            routes.append(current_route)
        else:
            # If not feasible, discard the route and try again
            remaining_customers.update(current_route[1:-1])
    
    # Return the solution
    return {"routes": routes, "metadata": {}}

