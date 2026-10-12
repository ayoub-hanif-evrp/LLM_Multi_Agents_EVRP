from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    n_customers = instance.n_customers
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle
    
    routes = []
    current_route = [depot_id]
    current_load = 0
    current_battery = vehicle.start_soc
    
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        if current_load + customer.demand > vehicle.capacity:
            routes.append(current_route)
            current_route = [depot_id]
            current_load = 0
            current_battery = vehicle.start_soc
        
        energy_needed = energy_required(instance.node_map[current_route[-1]], customer, vehicle)
        if current_battery < energy_needed:
            recharge_decision = full_recharge(vehicle, current_battery)
            current_battery = recharge_decision.battery_departure
            current_route.append(recharge_decision.station_id)
        
        current_route.append(customer_id)
        current_load += customer.demand
        current_battery -= energy_needed
    
    routes.append(current_route)
    
    return {
        "routes": routes,
        "metadata": {}
    }