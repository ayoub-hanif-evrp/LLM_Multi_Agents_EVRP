from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    routes = []
    for customer in instance.customers:
        route = [instance.depot_id, customer.id, instance.depot_id]
        routes.append(route)
    
    def insert_charging_stations(instance, route):
        vehicle = instance.vehicle
        total_energy_required = sum(energy_required(instance.node_map[route[i]], instance.node_map[route[i+1]], vehicle) for i in range(len(route)-1))
        initial_soc = vehicle.start_soc
        final_soc = full_recharge(vehicle, initial_soc + total_energy_required)
        
        if final_soc < vehicle.battery_capacity:
            for station in instance.stations:
                energy_to_station = energy_required(instance.node_map[route[-2]], instance.node_map[station.id], vehicle)
                energy_from_station = energy_required(instance.node_map[station.id], instance.node_map[route[-1]], vehicle)
                if energy_to_station + energy_from_station <= vehicle.battery_capacity - final_soc:
                    route.insert(-1, station.id)
                    break
    
    for route in routes:
        insert_charging_stations(instance, route)
    
    return {"routes": routes, "metadata": {}}