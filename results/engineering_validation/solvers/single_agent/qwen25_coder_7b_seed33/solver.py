from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    vehicle = instance.vehicle
    capacity = vehicle.capacity
    battery_capacity = vehicle.battery_capacity
    consumption_rate = vehicle.consumption_rate
    
    routes = [[depot_id]]
    for customer_id in customer_ids:
        routes[0].append(customer_id)
    routes[0].append(depot_id)
    
    return {"routes": routes, "metadata": {}}