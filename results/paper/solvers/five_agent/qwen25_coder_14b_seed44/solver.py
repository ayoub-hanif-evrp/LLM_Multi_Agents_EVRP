import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
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
    if all(stop_state.battery_departure >= 0 for stop_state in stop_states):
        return {"routes": [route], "metadata": {}}
    
    # If not feasible, try to insert charging stations
    for station_id in station_ids:
        # Insert station at every possible position
        for i in range(1, len(route)):
            new_route = route[:i] + [station_id] + route[i:]
            stop_states = propagate_route(instance, new_route)
            if all(stop_state.battery_departure >= 0 for stop_state in stop_states):
                return {"routes": [new_route], "metadata": {}}
    
    # If no feasible solution is found, return an empty solution
    return {"routes": [], "metadata": {}}