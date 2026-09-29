from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    routes = []
    for customer in instance.customers:
        route = [instance.depot_id, customer.id, instance.depot_id]
        routes.append(route)
    return {"routes": routes, "metadata": {}}