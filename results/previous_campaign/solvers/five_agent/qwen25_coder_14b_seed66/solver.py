import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize variables
    depot_id = instance.depot_id
    customer_ids = list(instance.customer_ids)
    station_ids = list(instance.station_ids)
    vehicle = instance.vehicle
    
    # Shuffle customers for randomness
    random.shuffle(customer_ids)
    
    # Create initial routes with depot at the start and end
    routes = [[depot_id] + [customer_ids.pop(0)] + [depot_id]]
    
    # Function to check if a route is valid
    def is_valid_route(route):
        stops = propagate_route(instance, route)
        for stop in stops:
            if stop.battery_departure < 0:
                return False
        return True
    
    # Function to add a customer to a route
    def add_customer_to_route(customer_id, route):
        best_position = None
        best_distance = float('inf')
        
        for i in range(1, len(route)):
            new_route = route[:i] + [customer_id] + route[i:]
            if is_valid_route(new_route):
                stops = propagate_route(instance, new_route)
                total_distance = stops[-1].distance_so_far
                if total_distance < best_distance:
                    best_distance = total_distance
                    best_position = i
        
        if best_position is not None:
            route.insert(best_position, customer_id)
            return True
        return False
    
    # Add remaining customers to routes
    while customer_ids:
        added = False
        for route in routes:
            if add_customer_to_route(customer_ids[0], route):
                customer_ids.pop(0)
                added = True
                break
        if not added:
            # If no route can accommodate the customer, create a new route
            routes.append([depot_id] + [customer_ids.pop(0)] + [depot_id])
    
    # Add charging stations if necessary
    for route in routes:
        stops = propagate_route(instance, route)
        for i in range(1, len(route) - 1):
            if stops[i].battery_departure < 0:
                # Insert a charging station
                route.insert(i, station_ids[0])
                break
    
    # Ensure all routes start and end at the depot
    for route in routes:
        if route[0] != depot_id:
            route.insert(0, depot_id)
        if route[-1] != depot_id:
            route.append(depot_id)
    
    # Metadata
    metadata = {
        "vehicle_capacity": vehicle.capacity,
        "battery_capacity": vehicle.battery_capacity,
        "consumption_rate": vehicle.consumption_rate,
        "velocity": vehicle.velocity,
        "inverse_refuel_rate": vehicle.inverse_refuel_rate,
        "start_soc": vehicle.start_soc,
        "total_routes": len(routes),
        "total_distance": sum(propagate_route(instance, route)[-1].distance_so_far for route in routes)
    }
    
    return {"routes": routes, "metadata": metadata}