from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    station_ids = instance.station_ids
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle
    
    def is_feasible(route):
        states = propagate_route(instance, route)
        for state in states:
            if state.battery_departure < 0:
                return False
        return True
    
    def find_nearest_station(customer, stations):
        nearest_station = None
        min_distance = float('inf')
        for station in stations:
            dist = distance(customer, station)
            if dist < min_distance:
                min_distance = dist
                nearest_station = station
        return nearest_station
    
    def insert_station(route, customer, station):
        index = route.index(customer)
        route.insert(index + 1, station.id)
        return route
    
    def repair_route(route):
        states = propagate_route(instance, route)
        for i in range(len(route) - 1):
            if states[i].battery_departure < 0:
                customer = instance.node_map[route[i]]
                station = find_nearest_station(customer, stations)
                route = insert_station(route, customer, station)
                states = propagate_route(instance, route)
        return route
    
    def solve_route(customers):
        route = [depot_id]
        for customer in customers:
            route.append(customer.id)
        route.append(depot_id)
        return route
    
    routes = []
    for customer in customers:
        route = solve_route([customer])
        route = repair_route(route)
        routes.append(route)
    
    return {"routes": routes, "metadata": {}}