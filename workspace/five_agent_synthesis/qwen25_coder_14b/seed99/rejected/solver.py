import random
import time
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution

def charging_strategy(instance, route):
    vehicle = instance.vehicle
    stop_states = propagate_route(instance, route)
    battery_capacity = vehicle.battery_capacity
    battery_on_arrival = vehicle.start_soc
    current_time = 0
    current_battery = battery_on_arrival
    current_route = []

    for stop_state in stop_states:
        node_id = stop_state.node_id
        node = instance.node_map[node_id]
        if node.kind == "station":
            charge_decision = full_recharge(vehicle, battery_on_arrival)
            current_battery = charge_decision.battery_departure
            current_time += charge_decision.duration
        else:
            current_time = max(current_time, node.ready_time)
            current_time += stop_state.service_time
            current_battery -= energy_required(instance.node_map[current_route[-1]], node, vehicle)

        if current_battery < 0:
            # Insert a station before the current node
            for station_id in instance.station_ids:
                station = instance.node_map[station_id]
                if energy_required(instance.node_map[current_route[-1]], station, vehicle) <= current_battery:
                    charge_decision = full_recharge(vehicle, current_battery)
                    current_battery = charge_decision.battery_departure
                    current_time += charge_decision.duration
                    current_route.append(station_id)
                    break

        current_route.append(node_id)
        battery_on_arrival = current_battery

    return current_route

def is_feasible(instance, routes):
    candidate = CandidateSolution(routes=routes)
    fault = first_fault(instance, candidate)
    return fault["family"] == "OK"

def initial_solution(instance):
    routes = []
    current_route = [instance.depot_id]
    current_load = 0
    current_battery = instance.vehicle.start_soc
    current_time = 0

    for customer_id in instance.customer_ids:
        customer = instance.node_map[customer_id]
        if current_load + customer.demand > instance.vehicle.capacity:
            routes.append(current_route + [instance.depot_id])
            current_route = [instance.depot_id]
            current_load = 0
            current_battery = instance.vehicle.start_soc
            current_time = 0

        if current_battery < energy_required(customer, instance.depot, instance.vehicle):
            # Ensure the vehicle has enough battery to reach the next charging station
            for station_id in instance.station_ids:
                station = instance.node_map[station_id]
                if energy_required(instance.node_map[current_route[-1]], station, vehicle) <= current_battery:
                    charge_decision = full_recharge(instance.vehicle, current_battery)
                    current_battery = charge_decision.battery_departure
                    current_time += charge_decision.duration
                    current_route.append(station_id)
                    break

        travel = travel_time(instance.node_map[current_route[-1]], customer, instance.vehicle)
        if current_time + travel < customer.ready_time:
            current_time = customer.ready_time

        current_time += travel
        current_battery -= energy_required(instance.node_map[current_route[-1]], customer, instance.vehicle)
        current_route.append(customer_id)
        current_load += customer.demand
        current_time += customer.service_time

    if current_route:
        routes.append(current_route + [instance.depot_id])

    return routes

def local_search(instance, routes):
    # Implement a simple local search to improve the solution
    # This is a placeholder for more sophisticated local search strategies
    return routes

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)

    initial_routes = initial_solution(instance)
    if not is_feasible(instance, initial_routes):
        raise ValueError("Initial solution is not feasible")

    best_routes = initial_routes
    best_metadata = {
        "feasibility": "OK",
        "vehicles": len(best_routes),
        "distance": sum(distance(instance.node_map[a], instance.node_map[b]) for route in best_routes for a, b in zip(route, route[1:]))
    }

    # Implement a search loop with time limit
    start_time = time.time()
    while time.time() - start_time < time_limit_s:
        candidate_routes = local_search(instance, best_routes)
        if is_feasible(instance, candidate_routes):
            candidate_distance = sum(distance(instance.node_map[a], instance.node_map[b]) for route in candidate_routes for a, b in zip(route, route[1:]))
            candidate_metadata = {
                "feasibility": "OK",
                "vehicles": len(candidate_routes),
                "distance": candidate_distance
            }
            if candidate_metadata["vehicles"] < best_metadata["vehicles"] or (candidate_metadata["vehicles"] == best_metadata["vehicles"] and candidate_distance < best_metadata["distance"]):
                best_routes = candidate_routes
                best_metadata = candidate_metadata

    return {"routes": best_routes, "metadata": best_metadata}