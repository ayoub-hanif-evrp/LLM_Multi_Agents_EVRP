from evrptw_autolab.problem.types import EVRPTWInstance
from evrptw_autolab.problem.physics import distance, energy_required, full_recharge, propagate_route
def greedy_charging(instance: EVRPTWInstance, route: list[str]) -> list[str]:
    stops = [instance.node_map[node_id] for node_id in route]
    current_soc = instance.vehicle.start_soc * instance.vehicle.battery_capacity
    new_route = []
    for stop in stops:
        if stop.kind == 'customer':
            energy_needed = energy_required(instance.depot, stop, instance.vehicle)
            if current_soc < energy_needed:
                station_id = find_nearest_station(instance, current_soc)
                full_recharge(instance.vehicle, current_soc)
                new_route.append(station_id)
                current_soc = instance.vehicle.battery_capacity
        new_route.append(stop.id)
    return new_route
def find_nearest_station(instance: EVRPTWInstance, current_soc: float) -> str:
    nearest_station = None
    min_distance = float('inf')
    for station in instance.stations:
        energy_needed = energy_required(station, instance.depot, instance.vehicle)
        if current_soc < energy_needed and distance(station, instance.depot) < min_distance:
            nearest_station = station.id
            min_distance = distance(station, instance.depot)
    return nearest_station