import numpy as np
from evrptw_autolab.problem.types import EVRPTWInstance, Node
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def charging(instance, route_index):
    # Get the current node and vehicle
    stop = instance.node_map[route_index[-1]]
    vehicle = instance.vehicle
    battery_on_arrival = stop.battery_arrival
    
    # Calculate the energy required for each leg of the route
    energy_required_list = [energy_required(instance.node_map[i], instance.node_map[i+1], vehicle) for i in range(len(route_index)-1)]
    
    # Sort the legs by energy required in descending order
    sorted_legs = sorted(enumerate(energy_required_list), key=lambda x: x[1], reverse=True)
    
    # Greedily select the leg with the highest energy required first
    greedy_route = [route_index[0]]
    current_energy = 0
    for i, (leg_index, energy) in sorted_legs:
        if current_energy + energy <= vehicle.battery_capacity * instance.vehicle.start_soc:
            greedy_route.append(instance.node_map[i+1])
            current_energy += energy
    
    # Propagate the route and update the stop state
    propagate_route(instance, greedy_route)
    for i in range(len(greedy_route)-1):
        stop = instance.node_map[greedy_route[i]]
        if stop.service_start != 0:
            stop.service_start = current_energy / vehicle.consumption_rate
        else:
            stop.service_start = current_energy / vehicle.consumption_rate
    
    return greedy_route
