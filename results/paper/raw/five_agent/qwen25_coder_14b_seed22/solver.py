import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import Node, VehicleSpec

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    def is_feasible(route):
        stops = propagate_route(instance, route)
        for stop in stops:
            if stop.battery_departure < 0:
                return False
        return True

    def construct_initial_routes():
        routes = []
        unvisited_customers = list(instance.customer_ids)
        while unvisited_customers:
            route = [instance.depot_id]
            current_node = instance.depot
            current_battery = instance.vehicle.start_soc
            current_load = 0
            while unvisited_customers:
                next_customer = None
                min_distance = float('inf')
                for customer_id in unvisited_customers:
                    customer = instance.node_map[customer_id]
                    if distance(current_node, customer) < min_distance:
                        next_customer = customer
                        min_distance = distance(current_node, customer)
                if next_customer is None:
                    break
                if current_load + next_customer.demand > instance.vehicle.capacity:
                    break
                if current_battery - energy_required(current_node, next_customer, instance.vehicle) < 0:
                    break
                route.append(next_customer.id)
                unvisited_customers.remove(next_customer.id)
                current_node = next_customer
                current_load += next_customer.demand
                current_battery -= energy_required(current_node, instance.depot, instance.vehicle)
            route.append(instance.depot_id)
            routes.append(route)
        return routes

    def optimize_routes(routes):
        # Simple optimization: try to swap adjacent nodes to improve feasibility
        improved = True
        while improved:
            improved = False
            for i in range(len(routes)):
                for j in range(1, len(routes[i]) - 1):
                    for k in range(j + 1, len(routes[i]) - 1):
                        new_route = routes[i].copy()
                        new_route[j], new_route[k] = new_route[k], new_route[j]
                        if is_feasible(new_route):
                            routes[i] = new_route
                            improved = True
        return routes

    initial_routes = construct_initial_routes()
    optimized_routes = optimize_routes(initial_routes)

    metadata = {
        "num_vehicles": len(optimized_routes),
        "total_distance": sum(distance(instance.node_map[route[i]], instance.node_map[route[i + 1]])
                               for route in optimized_routes for i in range(len(route) - 1))
    }

    return {"routes": optimized_routes, "metadata": metadata}