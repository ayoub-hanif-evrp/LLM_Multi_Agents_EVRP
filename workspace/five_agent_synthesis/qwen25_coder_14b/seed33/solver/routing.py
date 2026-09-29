from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution
import random
import time

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    start_time = time.time()

    def initial_route():
        route = [instance.depot_id]
        remaining_customers = list(instance.customer_ids)
        random.shuffle(remaining_customers)
        for customer in remaining_customers:
            route.append(customer)
        route.append(instance.depot_id)
        return route

    def is_feasible(route):
        stop_states = propagate_route(instance, route)
        for stop in stop_states:
            if stop.load > instance.vehicle.capacity:
                return False
            if stop.arrival_time > stop.node.service_end:
                return False
            if stop.battery_arrival < 0:
                return False
        return True

    def repair_route(route):
        stop_states = propagate_route(instance, route)
        for i, stop in enumerate(stop_states):
            if stop.load > instance.vehicle.capacity:
                # Remove customers until capacity is respected
                while stop.load > instance.vehicle.capacity:
                    route.pop(i)
                    stop_states = propagate_route(instance, route)
                    stop = stop_states[i]
            if stop.arrival_time > stop.node.service_end:
                # Remove customers until time window is respected
                while stop.arrival_time > stop.node.service_end:
                    route.pop(i)
                    stop_states = propagate_route(instance, route)
                    stop = stop_states[i]
            if stop.battery_arrival < 0:
                # Remove customers until battery is respected
                while stop.battery_arrival < 0:
                    route.pop(i)
                    stop_states = propagate_route(instance, route)
                    stop = stop_states[i]
        return route

    def construct_initial_solution():
        routes = []
        remaining_customers = list(instance.customer_ids)
        while remaining_customers:
            route = initial_route()
            feasible_route = repair_route(route)
            routes.append(feasible_route)
            remaining_customers = [c for c in remaining_customers if c not in feasible_route[1:-1]]
        return routes

    def calculate_energy_cost(route, instance):
        total_energy = 0
        current_node = instance.depot
        for next_node_id in route:
            next_node = instance.node_map[next_node_id]
            total_energy += energy_required(current_node, next_node, instance.vehicle)
            current_node = next_node
        return total_energy

    def is_feasible_route(route, instance):
        stop_states = propagate_route(instance, route)
        for stop in stop_states:
            if stop.battery_arrival < 0:
                return False
        return True

    def insert_station(route, instance):
        max_energy_deficit = 0
        best_insertion_index = -1
        best_station = None
        current_node = instance.depot
        current_energy = instance.vehicle.start_soc * instance.vehicle.battery_capacity

        for i, next_node_id in enumerate(route):
            next_node = instance.node_map[next_node_id]
            energy_cost = energy_required(current_node, next_node, instance.vehicle)
            current_energy -= energy_cost

            if current_energy < 0:
                energy_deficit = abs(current_energy)
                if energy_deficit > max_energy_deficit:
                    max_energy_deficit = energy_deficit
                    best_insertion_index = i
                    best_station = instance.station_ids[0]  # Assuming the first station is the best for simplicity

            current_node = next_node

        if best_insertion_index == -1:
            return route

        return route[:best_insertion_index] + [best_station] + route[best_insertion_index:]

    def ensure_feasibility(routes, instance):
        for i, route in enumerate(routes):
            if not is_feasible_route(route, instance):
                routes[i] = insert_station(route, instance)
        return routes

    def local_search(routes, instance):
        improved = True
        while improved:
            improved = False
            for i in range(len(routes)):
                route = routes[i]
                for j in range(1, len(route) - 1):
                    for k in range(j + 1, len(route) - 1):
                        new_route = route[:j] + route[k:k+1] + route[j+1:k] + route[j:j+1] + route[k+1:]
                        if is_feasible(new_route):
                            routes[i] = new_route
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
        return routes

    routes = construct_initial_solution()
    routes = ensure_feasibility(routes, instance)
    routes = local_search(routes, instance)

    return {
        "routes": routes,
        "metadata": {}
    }