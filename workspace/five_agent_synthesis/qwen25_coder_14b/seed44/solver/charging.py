from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def ensure_feasibility_and_energy(instance, routes):
    for route in routes:
        while not is_feasible(instance, route):
            route = insert_station(instance, route)
    return routes

def is_feasible(instance, route):
    stop_states = propagate_route(instance, route)
    for stop in stop_states:
        if stop.battery_arrival < 0:
            return False
    return True

def insert_station(instance, route):
    nearest_station = find_nearest_station(instance, route[-2])
    route.insert(-1, nearest_station)
    return route

def find_nearest_station(instance, node_id):
    node = instance.node_map[node_id]
    nearest_station = None
    min_distance = float('inf')
    for station in instance.stations:
        dist = distance(node, station)
        if dist < min_distance:
            min_distance = dist
            nearest_station = station.id
    return nearest_station