from typing import List, Tuple
from evrptw_autolab.problem.types import EVRPTWInstance, Node
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> dict:
    random.seed(seed)
    routes = build_routes(instance)
    return {"routes": routes, "metadata": {}}

def build_routes(instance: EVRPTWInstance) -> List[List[str]]:
    routes = []
    for customer in instance.customer_ids:
        routes.append([instance.depot_id, customer, instance.depot_id])
    return routes