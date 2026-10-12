import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution

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
    
    # Propagate the route to check feasibility
    stops = propagate_route(instance, route)
    
    # Check if the route is feasible
    if all(stop.battery_departure >= 0 for stop in stops):
        return {"routes": [route], "metadata": {"feasible": True}}
    
    # If not feasible, try inserting charging stations
    for i in range(1, len(route) - 1):
        for station_id in station_ids:
            new_route = route[:i] + [station_id] + route[i:]
            new_stops = propagate_route(instance, new_route)
            if all(stop.battery_departure >= 0 for stop in new_stops):
                return {"routes": [new_route], "metadata": {"feasible": True}}
    
    # If no feasible route is found, return an empty solution
    return {"routes": [], "metadata": {"feasible": False}}