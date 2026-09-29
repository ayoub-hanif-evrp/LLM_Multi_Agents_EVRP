from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def ensure_battery_feasibility(instance, routes, vehicle):
    for route in routes:
        stop_states = propagate_route(instance, route)
        for i, stop_state in enumerate(stop_states):
            if stop_state.battery_arrival < 0:
                route = insert_station(instance, route, route[i-1], vehicle)
                stop_states = propagate_route(instance, route)
    return routes

def insert_station(instance, route, node_id, vehicle):
    nearest_station = find_nearest_station(instance, node_id, vehicle)
    route.insert(route.index(node_id) + 1, nearest_station)
    return route

def find_nearest_station(instance, node_id, vehicle):
    nearest_station = None
    min_distance = float('inf')
    for station in instance.stations:
        d = distance(instance.node_map[node_id], station)
        if d < min_distance:
            min_distance = d
            nearest_station = station.id
    return nearest_station