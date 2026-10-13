import random
from typing import List, Dict, Tuple
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import EVRPTWInstance, CandidateSolution

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> CandidateSolution:
    """
    Solves the EVRPTW problem by constructing routes that visit each customer exactly once,
    respecting time windows, vehicle capacity, and battery constraints. Uses a simple insertion
    heuristic with charging station insertion when needed.
    """
    random.seed(seed)
    routes = []
    unserved = list(instance.customer_ids)
    vehicle = instance.vehicle

    while unserved:
        # Start a new route from the depot
        current_route = [instance.depot_id]
        current_load = 0.0
        current_battery = vehicle.start_soc * vehicle.battery_capacity
        current_time = 0.0

        # Try to insert customers into this route
        inserted = True
        while inserted:
            inserted = False
            best_customer = None
            best_position = -1
            best_cost = float('inf')

            for i, cust_id in enumerate(unserved):
                cust = instance.node_map[cust_id]
                # Try inserting at each possible position in the route
                for pos in range(len(current_route)):
                    # Check if insertion is possible at this position
                    if can_insert(instance, current_route, pos, cust_id, current_load, current_battery, current_time):
                        cost = insertion_cost(instance, current_route, pos, cust_id, current_load, current_battery, current_time)
                        if cost < best_cost:
                            best_cost = cost
                            best_customer = cust_id
                            best_position = pos

            if best_customer is not None:
                # Insert the best customer
                insert_customer(instance, current_route, best_position, best_customer, current_load, current_battery, current_time)
                unserved.remove(best_customer)
                inserted = True

        # Add depot at the end
        current_route.append(instance.depot_id)
        routes.append(current_route)

    return CandidateSolution(routes=routes)

def can_insert(instance: EVRPTWInstance, route: List[str], pos: int, cust_id: str, current_load: float, current_battery: float, current_time: float) -> bool:
    """
    Checks if a customer can be inserted at a given position in the route.
    """
    cust = instance.node_map[cust_id]
    vehicle = instance.vehicle

    # Get previous and next nodes
    prev_node = instance.node_map[route[pos-1]] if pos > 0 else instance.depot
    next_node = instance.node_map[route[pos]] if pos < len(route) else instance.depot

    # Check capacity
    if current_load + cust.demand > vehicle.capacity:
        return False

    # Check time window for previous leg
    prev_time = current_time
    travel_prev = travel_time(prev_node, cust, vehicle)
    if prev_time + travel_prev > cust.due_time:
        return False

    # Check battery for previous leg
    energy_prev = energy_required(prev_node, cust, vehicle)
    if current_battery - energy_prev < 0:
        return False

    # Check time window for next leg
    service_time = cust.service_time
    next_time = prev_time + travel_prev + service_time
    travel_next = travel_time(cust, next_node, vehicle)
    if next_time + travel_next > next_node.due_time:
        return False

    # Check battery for next leg
    energy_next = energy_required(cust, next_node, vehicle)
    if current_battery - energy_prev - energy_next < 0:
        return False

    return True

def insertion_cost(instance: EVRPTWInstance, route: List[str], pos: int, cust_id: str, current_load: float, current_battery: float, current_time: float) -> float:
    """
    Calculates the cost of inserting a customer at a given position.
    """
    cust = instance.node_map[cust_id]
    vehicle = instance.vehicle

    prev_node = instance.node_map[route[pos-1]] if pos > 0 else instance.depot
    next_node = instance.node_map[route[pos]] if pos < len(route) else instance.depot

    # Distance cost
    dist_prev = distance(prev_node, cust)
    dist_next = distance(cust, next_node)
    total_dist = dist_prev + dist_next

    # Time cost
    travel_prev = travel_time(prev_node, cust, vehicle)
    travel_next = travel_time(cust, next_node, vehicle)
    total_time = travel_prev + travel_next

    return total_dist + total_time

def insert_customer(instance: EVRPTWInstance, route: List[str], pos: int, cust_id: str, current_load: float, current_battery: float, current_time: float):
    """
    Inserts a customer into the route at the given position and updates the route state.
    """
    cust = instance.node_map[cust_id]
    vehicle = instance.vehicle

    # Update load
    new_load = current_load + cust.demand

    # Update battery and time
    prev_node = instance.node_map[route[pos-1]] if pos > 0 else instance.depot
    travel_time_prev = travel_time(prev_node, cust, vehicle)
    energy_prev = energy_required(prev_node, cust, vehicle)
    new_battery = current_battery - energy_prev
    new_time = current_time + travel_time_prev

    # Insert the customer
    route.insert(pos, cust_id)

    # Update state for next insertions
    return new_load, new_battery, new_time