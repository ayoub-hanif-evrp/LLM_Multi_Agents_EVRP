import numpy as np
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from typing import List, Tuple

capacity = 100  # Example capacity in kWh

def charge_vehicle(vehicle: str, battery_on_arrival: float) -> None:
    global capacity
    if battery_on_arrival < vehicle.capacity - capacity:
        capacity += battery_on_arrival
    else:
        capacity = vehicle.capacity


def solve(instance: evrptw_autolab.problem.types.EVRPTWInstance, seed: int, time_limit_s: float) -> dict:
    routes = []
    for i in range(len(instance.customer_ids)):
        route = [instance.depot_id]
        current_capacity = capacity
        for j in range(i + 1, len(instance.customer_ids)):
            if energy_required(instance.customers[j], instance.customers[i], instance.vehicle) <= current_capacity:
                route.append(instance.customers[j].id)
                current_capacity -= energy_required(instance.customers[j], instance.customers[i], instance.vehicle)
            else:
                break
        route.append(instance.depot_id)
        routes.append(route)
    return {'routes': routes, 'metadata': {'feasibility': 'improve'}}