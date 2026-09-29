import random
import time
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)

    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    n_customers = instance.n_customers
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle

    # Initialize routes
    routes = [[] for _ in range(n_customers)]

    # Function to calculate the total distance of a route
    def total_distance(route):
        return sum(distance(instance.node_map[route[i]], instance.node_map[route[i+1]]) for i in range(len(route)-1))

    # Function to calculate the total energy consumption of a route
    def total_energy_consumption(route):
        return sum(energy_required(instance.node_map[route[i]], instance.node_map[route[i+1]], vehicle) for i in range(len(route)-1))

    # Function to calculate the total number of vehicles used
    def total_vehicles(routes):
        return len([route for route in routes if route])

    # Function to calculate the total distance of all routes
    def total_distance_all_routes(routes):
        return sum(total_distance(route) for route in routes if route)

    # Function to calculate the total energy consumption of all routes
    def total_energy_consumption_all_routes(routes):
        return sum(total_energy_consumption(route) for route in routes if route)

    # Function to add a customer to a route
    def add_customer_to_route(route, customer_id):
        route.append(customer_id)

    # Function to remove a customer from a route
    def remove_customer_from_route(route, customer_id):
        route.remove(customer_id)

    # Function to evaluate a route
    def evaluate_route(route):
        if not route:
            return float('inf')
        return total_distance(route) + total_energy_consumption(route)

    # Function to evaluate all routes
    def evaluate_all_routes(routes):
        return sum(evaluate_route(route) for route in routes if route)

    # Function to repair a route
    def repair_route(route):
        if not route:
            return
        while len(route) > 1:
            customer_id = route.pop()
            if evaluate_route(route) < evaluate_route(route + [customer_id]):
                route.append(customer_id)
                break

    # Function to repair all routes
    def repair_all_routes(routes):
        for i in range(len(routes)):
            repair_route(routes[i])

    # Function to initialize routes
    def initialize_routes():
        for customer_id in customer_ids:
            routes[random.randint(0, n_customers-1)].append(customer_id)

    # Function to improve routes
    def improve_routes():
        for i in range(len(routes)):
            for j in range(len(routes)):
                if i == j:
                    continue
                for customer_id in routes[j]:
                    routes[i].append(customer_id)
                    routes[j].remove(customer_id)
                    if evaluate_route(routes[i]) < evaluate_route(routes[j]):
                        break
                    else:
                        routes[i].remove(customer_id)
                        routes[j].append(customer_id)

    # Function to repair and improve routes
    def repair_and_improve_routes():
        repair_all_routes(routes)
        improve_routes()

    # Main loop
    start_time = time.time()
    while time.time() - start_time < time_limit_s:
        repair_and_improve_routes()

    # Return the solution
    return {
        "routes": routes,
        "metadata": {
            "total_distance": total_distance_all_routes(routes),
            "total_energy_consumption": total_energy_consumption_all_routes(routes),
            "total_vehicles": total_vehicles(routes)
        }
    }