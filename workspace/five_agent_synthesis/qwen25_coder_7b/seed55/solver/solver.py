from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution
import random
import time

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    start_time = time.time()

    # Initialize routes
    routes = [[instance.depot_id] for _ in range(instance.n_customers)]

    # Routing heuristic
    for customer_id in instance.customer_ids:
        customer = instance.node_map[customer_id]
        best_route_index = None
        best_insert_position = None
        best_insert_distance = float('inf')
        for route_index, route in enumerate(routes):
            for insert_position in range(len(route)):
                new_route = route[:insert_position] + [customer_id] + route[insert_position:]
                new_route_distance = sum(distance(instance.node_map[new_route[i]], instance.node_map[new_route[i+1]]) for i in range(len(new_route)-1))
                if new_route_distance < best_insert_distance:
                    best_route_index = route_index
                    best_insert_position = insert_position
                    best_insert_distance = new_route_distance
        if best_route_index is not None:
            routes[best_route_index].insert(best_insert_position, customer_id)

    # Ensure all routes start and end at the depot
    for route in routes:
        if route[0] != instance.depot_id:
            route.insert(0, instance.depot_id)
        if route[-1] != instance.depot_id:
            route.append(instance.depot_id)

    # Charging heuristic
    for route in routes:
        current_soc = instance.vehicle.start_soc * instance.vehicle.battery_capacity
        for i in range(1, len(route) - 1):
            prev_node = instance.node_map[route[i-1]]
            current_node = instance.node_map[route[i]]
            energy_used = energy_required(prev_node, current_node, instance.vehicle)
            if current_soc - energy_used < 0:
                full_recharge(instance.vehicle, current_soc)
                current_soc = instance.vehicle.battery_capacity
            current_soc -= energy_used

    # Check feasibility
    candidate_solution = CandidateSolution(routes=routes)
    packet = first_fault(instance, candidate_solution)
    if packet["family"] != "OK":
        print(f"First-fault detected: {packet}")

    # Return solution
    return {"routes": routes, "metadata": {}}