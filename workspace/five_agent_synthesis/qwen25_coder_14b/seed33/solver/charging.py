from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def calculate_energy_cost(route, instance):
    total_energy = 0
    current_node = instance.depot
    for next_node_id in route:
        next_node = instance.node_map[next_node_id]
        total_energy += energy_required(current_node, next_node, instance.vehicle)
        current_node = next_node
    return total_energy

def is_feasible_route(route, instance):
    stop_states = propagate_route(instance, route)
    for stop in stop_states:
        if stop.battery_arrival < 0:
            return False
    return True

def insert_station(route, instance):
    max_energy_deficit = 0
    best_insertion_index = -1
    best_station = None
    current_node = instance.depot
    current_energy = instance.vehicle.start_soc * instance.vehicle.battery_capacity

    for i, next_node_id in enumerate(route):
        next_node = instance.node_map[next_node_id]
        energy_cost = energy_required(current_node, next_node, instance.vehicle)
        current_energy -= energy_cost

        if current_energy < 0:
            energy_deficit = abs(current_energy)
            if energy_deficit > max_energy_deficit:
                max_energy_deficit = energy_deficit
                best_insertion_index = i
                best_station = instance.station_ids[0]  # Assuming the first station is the best for simplicity

        current_node = next_node

    if best_insertion_index == -1:
        return route

    return route[:best_insertion_index] + [best_station] + route[best_insertion_index:]

def ensure_feasibility(routes, instance):
    for i, route in enumerate(routes):
        if not is_feasible_route(route, instance):
            routes[i] = insert_station(route, instance)
    return routes