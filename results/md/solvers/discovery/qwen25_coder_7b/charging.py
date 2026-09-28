from evrptw_autolab.problem.types import EVRPTWInstance
from evrptw_autolab.problem.physics import distance, energy_required, full_recharge, propagate_route
def greedy_charging(instance, route):
    for i in range(len(route) - 2):
        current_node = instance.node_map[route[i]]
        next_node = instance.node_map[route[i + 1]]
        station_id = find_nearest_station(instance, current_node, next_node)
        if station_id:
            route.insert(i + 1, station_id)
    return route

def find_nearest_station(instance, current_node, next_node):
    min_distance = float('inf')
    nearest_station = None
    for station in instance.stations:
        dist_to_current = distance(current_node, station)
        dist_to_next = distance(station, next_node)
        if dist_to_current + dist_to_next < min_distance:
            min_distance = dist_to_current + dist_to_next
            nearest_station = station.id
    return nearest_station