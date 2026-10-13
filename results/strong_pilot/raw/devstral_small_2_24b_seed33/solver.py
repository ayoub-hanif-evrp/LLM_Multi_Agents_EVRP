import random
from typing import List
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import EVRPTWInstance, Node, VehicleSpec, CandidateSolution

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> CandidateSolution:
    """Solve EVRPTW using a two-phase approach: initial route construction followed by charging insertion."""
    random.seed(seed)
    unserved = list(instance.customer_ids)
    routes = []
    vehicle = instance.vehicle

    # Phase 1: Build initial routes
    routes = build_initial_routes(instance, unserved)

    # Phase 2: Insert charging stops where needed
    routes = insert_charging_stops(instance, routes, vehicle)

    # Phase 3: Final validation and cleanup
    routes = finalize_solution(instance, routes, unserved)

    return CandidateSolution(routes=routes, metadata={"algorithm": "two_phase_with_charging"})

def build_initial_routes(instance: EVRPTWInstance, unserved: List[str]) -> List[List[str]]:
    """Build initial routes by grouping nearby customers with feasibility checks."""
    routes = []
    remaining = unserved.copy()
    vehicle = instance.vehicle

    while remaining:
        route = [instance.depot_id]
        current_load = 0.0
        current_time = 0.0
        current_battery = vehicle.start_soc * vehicle.battery_capacity
        current_node = instance.depot

        # Try to add customers to this route
        candidates = remaining.copy()
        random.shuffle(candidates)

        for customer_id in candidates:
            customer = instance.node_map[customer_id]
            
            # Check capacity
            if current_load + customer.demand > vehicle.capacity:
                continue
            
            # Check time window feasibility
            travel = travel_time(current_node, customer, vehicle)
            arrival = current_time + travel
            if arrival > customer.due_time:
                continue
            
            # Check battery feasibility
            energy_needed = energy_required(current_node, customer, vehicle)
            if current_battery < energy_needed:
                continue
            
            # If all checks pass, add to route
            route.append(customer_id)
            current_load += customer.demand
            current_time = arrival + customer.service_time
            current_battery -= energy_needed
            current_node = customer
            remaining.remove(customer_id)

        # Complete the route with depot
        if len(route) > 2:  # Only add if we actually added customers
            route.append(instance.depot_id)
            routes.append(route)

    return routes

def insert_charging_stops(instance: EVRPTWInstance, routes: List[List[str]], vehicle: VehicleSpec) -> List[List[str]]:
    """Insert charging stops where battery would be insufficient."""
    new_routes = []

    for route in routes:
        new_route = route.copy()
        stops = propagate_route(instance, new_route)

        # Check each segment for battery sufficiency
        for i in range(len(stops) - 1):
            current = stops[i]
            next_node = stops[i+1]

            energy_needed = energy_required(
                instance.node_map[current.node_id],
                instance.node_map[next_node.node_id],
                vehicle
            )

            if current.battery_departure < energy_needed:
                # Find nearest charging station
                nearest_station = None
                min_dist = float('inf')

                for station_id in instance.station_ids:
                    station = instance.node_map[station_id]
                    dist = distance(instance.node_map[current.node_id], station)
                    if dist < min_dist:
                        min_dist = dist
                        nearest_station = station_id

                if nearest_station:
                    insert_pos = new_route.index(current.node_id) + 1
                    new_route.insert(insert_pos, nearest_station)
                    # Recalculate stops after insertion
                    stops = propagate_route(instance, new_route)

        new_routes.append(new_route)

    return new_routes

def finalize_solution(instance: EVRPTWInstance, routes: List[List[str]], unserved: List[str]) -> List[List[str]]:
    """Final validation and cleanup of routes."""
    # Remove any unserved customers by creating individual routes
    for customer_id in unserved:
        route = [instance.depot_id, customer_id, instance.depot_id]
        routes.append(route)

    # Validate all routes
    valid_routes = []
    for route in routes:
        if is_valid_route(instance, route):
            valid_routes.append(route)

    return valid_routes

def is_valid_route(instance: EVRPTWInstance, route: List[str]) -> bool:
    """Check if a route is valid (starts/ends at depot, all customers served once)."""
    if route[0] != instance.depot_id or route[-1] != instance.depot_id:
        return False

    served = set()
    for node_id in route[1:-1]:
        if node_id in instance.customer_ids:
            if node_id in served:
                return False
            served.add(node_id)

    return True

