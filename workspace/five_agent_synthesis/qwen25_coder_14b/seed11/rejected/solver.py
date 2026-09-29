import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    def is_feasible(routes):
        candidate = CandidateSolution(routes=routes)
        fault = first_fault(instance, candidate)
        return fault["family"] == "OK"
    
    def initial_solution():
        routes = []
        vehicle = instance.vehicle
        current_route = [instance.depot_id]
        current_load = 0
        current_battery = vehicle.start_soc
        
        for customer_id in instance.customer_ids:
            customer = instance.node_map[customer_id]
            if current_load + customer.demand > vehicle.capacity:
                current_route.append(instance.depot_id)
                routes.append(current_route)
                current_route = [instance.depot_id]
                current_load = 0
                current_battery = vehicle.start_soc
            
            if current_battery < energy_required(customer, instance.node_map[instance.depot_id], vehicle):
                charge_decision = full_recharge(vehicle, current_battery)
                current_battery = charge_decision.battery_departure
                current_route.append(instance.depot_id)
            
            current_route.append(customer_id)
            current_load += customer.demand
            current_battery -= energy_required(customer, instance.node_map[instance.depot_id], vehicle)
        
        if current_route:
            current_route.append(instance.depot_id)
            routes.append(current_route)
        
        return routes
    
    def charging_strategy(route):
        vehicle = instance.vehicle
        stop_states = propagate_route(instance, route)
        current_battery = vehicle.start_soc
        new_route = []
        
        for i, stop_state in enumerate(stop_states):
            if stop_state.node_id in instance.station_ids:
                # Full recharge at station
                charge_decision = full_recharge(vehicle, stop_state.battery_arrival)
                current_battery = charge_decision.battery_departure
            else:
                # Check if we need to go to a station before the next customer
                if i < len(stop_states) - 1:
                    next_node = instance.node_map[stop_states[i + 1].node_id]
                    energy_needed = energy_required(instance.node_map[stop_state.node_id], next_node, vehicle)
                    if current_battery < energy_needed:
                        # Find the nearest station
                        nearest_station = min(
                            instance.stations,
                            key=lambda station: distance(instance.node_map[stop_state.node_id], station)
                        )
                        # Add the station to the route
                        new_route.append(nearest_station.id)
                        # Full recharge at the nearest station
                        charge_decision = full_recharge(vehicle, current_battery)
                        current_battery = charge_decision.battery_departure
            
            new_route.append(stop_state.node_id)
            current_battery -= energy_required(instance.node_map[stop_state.node_id], stop_states[i + 1].node_id, vehicle) if i < len(stop_states) - 1 else 0
        
        return new_route
    
    def local_search(routes):
        # Placeholder for local search logic
        return routes
    
    def construct_solution():
        routes = initial_solution()
        for i in range(len(routes)):
            routes[i] = charging_strategy(routes[i])
        routes = local_search(routes)
        return routes
    
    routes = construct_solution()
    
    if not is_feasible(routes):
        raise ValueError("Initial solution is not feasible")
    
    return {"routes": routes, "metadata": {}}