import random
from typing import List, Dict
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import EVRPTWInstance, Node, VehicleSpec, CandidateSolution

# Module-level helper functions
def get_node(node_id: str, instance: EVRPTWInstance) -> Node:
    return instance.node_map[node_id]

def is_customer(node_id: str, instance: EVRPTWInstance) -> bool:
    return node_id in instance.customer_ids

def is_station(node_id: str, instance: EVRPTWInstance) -> bool:
    return node_id in instance.station_ids

def is_depot(node_id: str, instance: EVRPTWInstance) -> bool:
    return node_id == instance.depot_id

def create_route(depot_id: str) -> List[str]:
    return [depot_id, depot_id]  # Always starts and ends at depot

def route_distance(route: List[str], instance: EVRPTWInstance) -> float:
    dist = 0.0
    for i in range(len(route) - 1):
        dist += distance(get_node(route[i], instance), get_node(route[i+1], instance))
    return dist

def route_energy(route: List[str], instance: EVRPTWInstance) -> float:
    energy = 0.0
    for i in range(len(route) - 1):
        energy += energy_required(get_node(route[i], instance), get_node(route[i+1], instance), instance.vehicle)
    return energy

def is_feasible_route(route: List[str], instance: EVRPTWInstance) -> bool:
    # Check depot constraints first
    if route[0] != instance.depot_id or route[-1] != instance.depot_id:
        return False

    # Check capacity
    current_load = 0.0
    for node_id in route[1:-1]:  # Skip depots
        current_load += get_node(node_id, instance).demand
        if current_load > instance.vehicle.capacity:
            return False

    # Check time windows and battery
    stops = propagate_route(instance, route)
    for stop in stops:
        node = get_node(stop.node_id, instance)
        if stop.arrival_time < node.ready_time or stop.arrival_time > node.due_time:
            return False
        if stop.battery_arrival < 0:
            return False

    return True

def insert_customer(route: List[str], customer_id: str, instance: EVRPTWInstance) -> bool:
    best_pos = -1
    best_cost = float('inf')

    for i in range(1, len(route)):  # Don't insert at start (depot)
        new_route = route[:i] + [customer_id] + route[i:]
        if is_feasible_route(new_route, instance):
            cost = route_distance(new_route, instance)
            if cost < best_cost:
                best_cost = cost
                best_pos = i

    if best_pos != -1:
        route.insert(best_pos, customer_id)
        return True
    return False

def insert_charging_station(route: List[str], instance: EVRPTWInstance) -> bool:
    stops = propagate_route(instance, route)
    for stop in stops:
        if stop.battery_arrival < 0:
            # Find best station insertion point
            best_station = None
            best_pos = -1
            best_cost = float('inf')

            for station_id in instance.station_ids:
                for i in range(1, len(route)):
                    new_route = route[:i] + [station_id] + route[i:]
                    new_stops = propagate_route(instance, new_route)
                    feasible = True
                    for s in new_stops:
                        if s.battery_arrival < 0:
                            feasible = False
                            break
                    if feasible:
                        cost = route_distance(new_route, instance)
                        if cost < best_cost:
                            best_cost = cost
                            best_station = station_id
                            best_pos = i

            if best_station is not None:
                route.insert(best_pos, best_station)
                return True
    return False

def build_route(instance: EVRPTWInstance, customers: List[str]) -> List[str]:
    route = create_route(instance.depot_id)
    random.shuffle(customers)

    for customer_id in customers:
        if not insert_customer(route, customer_id, instance):
            # If can't insert, create new route
            return [customer_id]  # Will be wrapped in depot later

    # Check if route needs charging
    if not is_feasible_route(route, instance):
        insert_charging_station(route, instance)

    return route

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> Dict:
    """Solve the EVRPTW problem with charging station support."""
    random.seed(seed)
    routes = []
    remaining_customers = list(instance.customer_ids)
    random.shuffle(remaining_customers)

    while remaining_customers:
        # Try to build a route with up to 10 customers
        batch_size = min(10, len(remaining_customers))
        batch = remaining_customers[:batch_size]

        route = build_route(instance, batch)

        # Ensure route starts and ends with depot
        if route[0] != instance.depot_id:
            route.insert(0, instance.depot_id)
        if route[-1] != instance.depot_id:
            route.append(instance.depot_id)

        if is_feasible_route(route, instance):
            routes.append(route)
            remaining_customers = remaining_customers[batch_size:]
        else:
            # If route not feasible, split into smaller batches
            batch_size = max(1, batch_size // 2)
            remaining_customers = batch + remaining_customers[batch_size:]

    return {"routes": routes, "metadata": {}}