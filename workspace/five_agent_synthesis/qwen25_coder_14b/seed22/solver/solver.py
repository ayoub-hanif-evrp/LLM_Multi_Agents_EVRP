from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with each customer visited exactly once
    routes = [[instance.depot_id, customer_id, instance.depot_id] for customer_id in instance.customer_ids]
    
    # Check for feasibility
    def is_feasible(routes):
        packet = first_fault(instance, CandidateSolution(routes=routes))
        return packet["family"] == "OK"
    
    # If the initial routes are not feasible, try to fix them
    if not is_feasible(routes):
        # Simple repair mechanism: try to swap customers within routes
        for route in routes:
            for i in range(1, len(route) - 1):
                for j in range(i + 1, len(route) - 1):
                    # Swap customers
                    route[i], route[j] = route[j], route[i]
                    if is_feasible(routes):
                        break
                else:
                    continue
                break
    
    # Ensure all customers are visited exactly once
    all_customers = set(instance.customer_ids)
    visited_customers = set()
    for route in routes:
        visited_customers.update(route[1:-1])
    
    if visited_customers != all_customers:
        # If not, add missing customers to routes
        for customer_id in all_customers - visited_customers:
            routes[0].insert(-1, customer_id)
    
    # Further optimization: try to reduce the number of vehicles
    def reduce_vehicles(routes):
        # Implement a simple heuristic to merge routes if possible
        new_routes = []
        for route in routes:
            if not new_routes:
                new_routes.append(route)
                continue
            last_route = new_routes[-1]
            if distance(instance.node_map[last_route[-2]], instance.node_map[route[1]], instance.vehicle) <= instance.vehicle.battery_capacity:
                last_route.extend(route[1:])
            else:
                new_routes.append(route)
        return new_routes
    
    routes = reduce_vehicles(routes)
    
    return {"routes": routes, "metadata": {}}