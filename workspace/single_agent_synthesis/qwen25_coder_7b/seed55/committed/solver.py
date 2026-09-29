from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    depot = instance.depot
    vehicle = instance.vehicle
    
    routes = [[depot_id]]
    for customer_id in customer_ids:
        routes[0].append(customer_id)
    routes[0].append(depot_id)
    
    solution = {"routes": routes, "metadata": {}}
    packet = first_fault(instance, CandidateSolution(routes=solution["routes"]))
    
    if packet["family"] != "OK":
        print(f"First fault: {packet}")
    
    return solution