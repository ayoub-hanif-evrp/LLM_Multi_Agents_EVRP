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
    node_map = instance.node_map

    # Initialize routes with the depot
    routes = [[depot_id] for _ in range(len(customers) + 1)]

    # Helper function to calculate the total distance of a route
    def total_distance(route):
        return sum(distance(node_map[route[i]], node_map[route[i + 1]]) for i in range(len(route) - 1))

    # Helper function to insert a charge station into a route
    def insert_charge(route, station_id):
        best_insertion_index = -1
        best_insertion_distance = float('inf')
        for i in range(len(route) - 1):
            new_route = route[:i + 1] + [station_id] + route[i + 1:]
            new_distance = total_distance(new_route)
            if new_distance < best_insertion_distance:
                best_insertion_distance = new_distance
                best_insertion_index = i + 1
        return route[:best_insertion_index + 1] + [station_id] + route[best_insertion_index + 1:]

    # Helper function to assign customers to routes
    def assign_customers(customers, routes):
        for customer in customers:
            min_distance = float('inf')
            best_route_index = -1
            for i, route in enumerate(routes):
                new_route = route + [customer.id]
                new_distance = total_distance(new_route)
                if new_distance < min_distance:
                    min_distance = new_distance
                    best_route_index = i
            routes[best_route_index].append(customer.id)
        return routes

    # Assign customers to routes
    routes = assign_customers(customers, routes)

    # Insert charge stations into routes
    for route in routes:
        for station in stations:
            if station.id not in route:
                route = insert_charge(route, station.id)

    # Ensure routes end at the depot
    for i, route in enumerate(routes):
        if route[-1] != depot_id:
            routes[i].append(depot_id)

    # Return the solution
    return {"routes": routes, "metadata": {}}

def build_routes(instance, vehicle, depot_id, customer_ids, station_ids, customers, stations):
    routes = []
    remaining_customers = set(customer_ids)
    current_route = [depot_id]
    current_battery = vehicle.start_soc

    while remaining_customers:
        best_customer = None
        best_distance = float('inf')
        for customer_id in remaining_customers:
            customer = instance.node_map[customer_id]
            dist = distance(depot, customer)
            if dist < best_distance:
                best_customer = customer_id
                best_distance = dist

        if best_customer:
            current_route.append(best_customer)
            remaining_customers.remove(best_customer)
        else:
            break

        current_route.append(depot_id)
        routes.append(current_route)
        current_route = [depot_id]
        current_battery = vehicle.start_soc

    return routes

