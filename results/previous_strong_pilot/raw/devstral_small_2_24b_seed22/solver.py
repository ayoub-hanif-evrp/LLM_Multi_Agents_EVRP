import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    """
    Solves the EVRPTW problem with battery-aware route construction.
    Uses a two-phase approach: initial route building with capacity/time constraints,
    followed by battery feasibility repair with station insertions.
    """
    random.seed(seed)
    routes = []
    unserved = list(instance.customer_ids)

    # Phase 1: Build initial routes ignoring battery constraints
    while unserved:
        route = [instance.depot_id]
        current_load = 0.0

        while unserved:
            # Find nearest unserved customer that fits capacity
            nearest = None
            min_dist = float('inf')
            for cid in unserved:
                node = instance.node_map[cid]
                dist = distance(instance.node_map[route[-1]], node)
                if dist < min_dist and current_load + node.demand <= instance.vehicle.capacity:
                    nearest = cid
                    min_dist = dist

            if nearest is None:
                break

            route.append(nearest)
            current_load += instance.node_map[nearest].demand
            unserved.remove(nearest)

        route.append(instance.depot_id)
        routes.append(route)

    # Phase 2: Repair battery feasibility
    feasible_routes = []
    for route in routes:
        repaired_route = repair_battery_constraints(instance, route)
        if repaired_route:
            feasible_routes.append(repaired_route)

    return CandidateSolution(routes=feasible_routes)

def repair_battery_constraints(instance, route):
    """
    Repairs a route to satisfy battery constraints by inserting charging stations.
    Returns None if the route cannot be made feasible.
    """
    # Simulate the route to identify battery violations
    stops = propagate_route(instance, route)
    
    # Check for battery violations
    for i, stop in enumerate(stops):
        if stop.battery_arrival < 0:
            # Battery violation found - try to insert charging before this stop
            return insert_charging_before(instance, route, i)
    
    return route if stops else None

def insert_charging_before(instance, route, violation_index):
    """
    Inserts charging stations before a violation point in the route.
    Returns the repaired route or None if repair fails.
    """
    # Get the node where violation occurs
    violated_node = instance.node_map[route[violation_index]]
    
    # Find the last valid stop before violation
    last_valid_index = violation_index - 1
    while last_valid_index >= 0:
        node_id = route[last_valid_index]
        node = instance.node_map[node_id]
        if node.kind == 'depot' or node.kind == 'station':
            break
        last_valid_index -= 1
    
    if last_valid_index < 0:
        return None  # Can't repair from start
    
    last_node = instance.node_map[route[last_valid_index]]
    
    # Find nearest charging station
    nearest_station = None
    min_dist = float('inf')
    for sid in instance.station_ids:
        station = instance.node_map[sid]
        dist = distance(last_node, station)
        if dist < min_dist:
            nearest_station = sid
            min_dist = dist
    
    if not nearest_station:
        return None  # No stations available
    
    # Create new route with charging station
    new_route = route[:last_valid_index+1] + [nearest_station] + route[last_valid_index+1:]
    
    # Verify the repair works
    stops = propagate_route(instance, new_route)
    for i, stop in enumerate(stops):
        if stop.battery_arrival < 0:
            return None  # Repair didn't work
    
    return new_route

def build_routes(instance, seed: int):
    """
    Helper function to build initial routes without considering battery constraints.
    """
    random.seed(seed)
    routes = []
    unserved = list(instance.customer_ids)

    while unserved:
        route = [instance.depot_id]
        current_load = 0.0

        while unserved:
            # Find nearest unserved customer
            nearest = None
            min_dist = float('inf')
            for cid in unserved:
                dist = distance(instance.node_map[route[-1]], instance.node_map[cid])
                if dist < min_dist and current_load + instance.node_map[cid].demand <= instance.vehicle.capacity:
                    nearest = cid
                    min_dist = dist

            if nearest is None:
                break

            route.append(nearest)
            current_load += instance.node_map[nearest].demand
            unserved.remove(nearest)

        route.append(instance.depot_id)
        routes.append(route)

    return routes

def insert_charge(instance, route, customer_id, current_battery, energy_needed):
    """
    Helper function to insert a charging station into a route if needed.
    Returns the modified route if charging was inserted, None otherwise.
    """
    node = instance.node_map[customer_id]
    last_node = instance.node_map[route[-1]]
    
    # Find the nearest charging station
    nearest_station = None
    min_dist = float('inf')
    for sid in instance.station_ids:
        station = instance.node_map[sid]
        dist = distance(last_node, station)
        if dist < min_dist:
            nearest_station = sid
            min_dist = dist
    
    if not nearest_station:
        return None
    
    # Check if we can reach the station with current battery
    station = instance.node_map[nearest_station]
    energy_to_station = energy_required(last_node, station, instance.vehicle)
    if current_battery < energy_to_station:
        return None
    
    # Insert the station into the route
    new_route = route.copy()
    new_route.append(nearest_station)
    
    # Update battery state after charging
    charge_decision = full_recharge(instance.vehicle, current_battery - energy_to_station)
    new_battery = charge_decision.battery_departure
    
    # Check if we can now reach the customer
    energy_to_customer = energy_required(station, node, instance.vehicle)
    if new_battery < energy_to_customer:
        return None
    
    return new_route



