import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id] for _ in range(int(instance.vehicle.capacity))]
    
    # Assign customers to routes
    for customer_id in instance.customer_ids:
        route = min(routes, key=lambda r: distance(instance.node_map[r[-1]], instance.node_map[customer_id]))
        route.append(customer_id)
        route.append(instance.depot_id)
    
    # Check feasibility
    candidate_solution = CandidateSolution(routes=routes)
    fault = first_fault(instance, candidate_solution)
    
    if fault["family"] != "OK":
        # If there's a fault, try to fix it by recharging at stations
        for route in routes:
            for i in range(1, len(route) - 1):
                if fault["node_id"] == route[i]:
                    # Insert a recharge at the nearest station
                    nearest_station = min(instance.stations, key=lambda s: distance(instance.node_map[route[i]], s))
                    route.insert(i + 1, nearest_station.id)
                    break
    
    # Final check
    candidate_solution = CandidateSolution(routes=routes)
    fault = first_fault(instance, candidate_solution)
    
    if fault["family"] != "OK":
        # If still not feasible, return an empty solution
        return {"routes": [], "metadata": {}}
    
    return {"routes": routes, "metadata": {}}