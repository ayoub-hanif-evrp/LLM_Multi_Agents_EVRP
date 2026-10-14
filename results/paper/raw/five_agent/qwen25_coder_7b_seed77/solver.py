import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    station_ids = instance.station_ids
    depot = instance.depot
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle
    
    # Initialize routes with the depot
    routes = [[depot_id] for _ in range(len(customers))]
    
    # Shuffle customers to randomize the order
    random.shuffle(customer_ids)
    
    # Assign customers to routes
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        best_route_index = None
        best_route_distance = float('inf')
        
        for i, route in enumerate(routes):
            if len(route) == 1:  # Only consider routes that start at the depot
                current_route = route + [customer_id]
                current_distance = sum(distance(instance.node_map[route[-1]], instance.node_map[next_id]) for next_id in current_route)
                if current_distance < best_route_distance:
                    best_route_index = i
                    best_route_distance = current_distance
        
        if best_route_index is not None:
            routes[best_route_index].append(customer_id)
    
    # Add the depot back to the end of each route
    for i in range(len(routes)):
        routes[i].append(depot_id)
    
    # Convert routes to list of string node IDs
    routes = [[str(node_id) for node_id in route] for route in routes]
    
    # Insert charging stations
    routes = insert_charges(instance, routes)
    
    return {"routes": routes, "metadata": {}}

def insert_charges(instance, routes):
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    station_ids = instance.station_ids
    depot = instance.depot
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle
    
    for route in routes:
        if depot_id in route:
            route_index = routes.index(route)
            for customer_id in customer_ids:
                customer = instance.node_map[customer_id]
                if customer.kind == 'customer':
                    current_route = route + [customer_id]
                    current_distance = sum(distance(instance.node_map[route[-1]], instance.node_map[next_id]) for next_id in current_route)
                    if current_distance > vehicle.battery_capacity / vehicle.start_soc:
                        routes[route_index].insert(routes[route_index].index(customer_id), random.choice(station_ids))
    return routes