import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize variables
    depot_id = instance.depot_id
    customer_ids = list(instance.customer_ids)
    station_ids = list(instance.station_ids)
    vehicle = instance.vehicle
    
    # Shuffle customers to create a random initial solution
    random.shuffle(customer_ids)
    
    # Create a single route with all customers
    route = [depot_id] + customer_ids + [depot_id]
    
    # Check if the initial route is feasible
    stop_states = propagate_route(instance, route)
    if any(stop_state.battery_departure < 0 for stop_state in stop_states):
        return {"routes": [], "metadata": {"feasible": False}}
    
    # Return the initial route as the solution
    return {"routes": [route], "metadata": {"feasible": True}}