import random
from typing import List, Tuple, Dict

from evrptw_autolab.problem.types import EVRPTWInstance, VehicleSpec, Node
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> Dict[str, List[List[str]]]:
    random.seed(seed)
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    station_ids = instance.station_ids
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle

    routes = build_routes(instance, vehicle)

    return {"routes": routes, "metadata": {}}

def insert_charges(route: List[str], station_id: str, vehicle: VehicleSpec) -> List[str]:
    best_insertion = None
    best_cost = float('inf')
    for i in range(len(route)):
        cost = travel_time(instance.node_map[route[i]], instance.node_map[station_id], vehicle) + travel_time(instance.node_map[station_id], instance.node_map[route[(i + 1) % len(route)]], vehicle)
        if cost < best_cost:
            best_cost = cost
            best_insertion = i
    route.insert(best_insertion + 1, station_id)
    return route

def build_routes(instance: EVRPTWInstance, vehicle: VehicleSpec) -> List[List[str]]:
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    station_ids = instance.station_ids
    customers = instance.customers
    stations = instance.stations

    routes = [[depot_id]]

    for customer_id in customer_ids:
        best_route = None
        best_cost = float('inf')
        for route in routes:
            cost = travel_time(instance.node_map[route[-1]], instance.node_map[customer_id], vehicle)
            if cost < best_cost:
                best_cost = cost
                best_route = route
        best_route.append(customer_id)

    for station_id in station_ids:
        best_route = None
        best_cost = float('inf')
        for route in routes:
            cost = travel_time(instance.node_map[route[-1]], instance.node_map[station_id], vehicle)
            if cost < best_cost:
                best_cost = cost
                best_route = route
        best_route.append(station_id)

    for route in routes:
        if route[-1] != depot_id:
            route.append(depot_id)

    return routes



