import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)

    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    station_ids = instance.station_ids
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle

    # Initialize routes
    routes = [[] for _ in range(instance.n_customers)]

    # Helper function to calculate the total distance of a route
    def total_distance(route):
        return sum(distance(instance.node_map[route[i]], instance.node_map[route[i+1]]) for i in range(len(route)-1))

    # Helper function to insert a charge station into a route
    def insert_charge(route, station_id):
        for i in range(len(route)-1):
            if energy_required(instance.node_map[route[i]], instance.node_map[route[i+1]], vehicle) > vehicle.battery_capacity:
                routes[routes.index(route)].insert(i+1, station_id)
                return True
        return False

    # Helper function to find the best insertion point for a customer
    def best_insertion_point(route, customer_id):
        best_index = -1
        best_distance = float('inf')
        for i in range(len(route)-1):
            if energy_required(instance.node_map[route[i]], instance.node_map[route[i+1]], vehicle) + energy_required(instance.node_map[route[i]], instance.node_map[customer_id], vehicle) > vehicle.battery_capacity:
                continue
            new_route = route[:i+1] + [customer_id] + route[i+1:]
            new_distance = total_distance(new_route)
            if new_distance < best_distance:
                best_distance = new_distance
                best_index = i
        return best_index

    # Main loop to build routes
    for customer_id in customer_ids:
        best_route = None
        best_distance = float('inf')
        for route in routes:
            if best_insertion_point(route, customer_id) != -1:
                new_route = route[:]
                new_route.insert(best_insertion_point(route, customer_id) + 1, customer_id)
                new_distance = total_distance(new_route)
                if new_distance < best_distance:
                    best_route = new_route
                    best_distance = new_distance
        if best_route:
            routes[routes.index(best_route)].append(customer_id)
        else:
            routes[0].append(customer_id)

    # Insert charge stations
    for i, route in enumerate(routes):
        for station_id in station_ids:
            if insert_charge(route, station_id):
                break

    # Ensure depot is at the end of each route
    for i, route in enumerate(routes):
        if route[-1] != depot_id:
            routes[i].append(depot_id)
        if route[0] != depot_id:
            routes[i].insert(0, depot_id)

    # Ensure the vehicle is fully charged before reaching the depot
    for i, route in enumerate(routes):
        if route[-1] == depot_id:
            route.insert(1, station_ids[0])

    # Final check to ensure all customers are visited exactly once
    visited_customers = set()
    for route in routes:
        for node_id in route:
            if node_id.startswith('C'):
                visited_customers.add(node_id)
    if len(visited_customers) != len(customer_ids):
        raise ValueError("Not all customers are visited exactly once")

    return {"routes": routes, "metadata": {}}


