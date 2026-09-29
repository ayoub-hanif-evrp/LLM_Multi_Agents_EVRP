from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def greedy_charging(instance, seed):
    # Initialize the solution
    routes = [[] for _ in range(instance.vehicle.capacity)]
    current_vehicle = 0
    current_capacity = [0] * instance.vehicle.capacity

    # Sort stations by their energy requirements in descending order
    stations = sorted(instance.stations, key=lambda s: s.energy_requirement, reverse=True)

    # Assign customers to vehicles
    for station in stations:
        if current_capacity[current_vehicle] + station.energy_requirement <= instance.vehicle.battery_capacity:
            routes[current_vehicle].append(station.id)
            current_capacity[current_vehicle] += station.energy_requirement
            current_vehicle = (current_vehicle + 1) % instance.vehicle.capacity

    return {"routes": routes, "metadata": {}}