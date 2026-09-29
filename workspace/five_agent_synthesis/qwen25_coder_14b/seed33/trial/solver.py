import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    def initial_routes(instance):
        routes = []
        current_route = [instance.depot_id]
        current_load = 0
        current_battery = instance.vehicle.start_soc
        current_time = 0
        
        for customer_id in instance.customer_ids:
            customer = instance.node_map[customer_id]
            if current_load + customer.demand > instance.vehicle.capacity:
                routes.append(current_route + [instance.depot_id])
                current_route = [instance.depot_id]
                current_load = 0
                current_battery = instance.vehicle.start_soc
                current_time = 0
            
            if current_battery - energy_required(instance.node_map[current_route[-1]], customer, instance.vehicle) < 0:
                charge_decision = full_recharge(instance.vehicle, current_battery)
                current_time += charge_decision.duration
                current_battery = charge_decision.battery_departure
            
            current_time += travel_time(instance.node_map[current_route[-1]], customer, instance.vehicle)
            current_battery -= energy_required(instance.node_map[current_route[-1]], customer, instance.vehicle)
            current_load += customer.demand
            
            current_route.append(customer_id)
        
        if current_route:
            routes.append(current_route + [instance.depot_id])
        
        return routes

    def is_feasible(routes):
        candidate_solution = CandidateSolution(routes=routes)
        fault = first_fault(instance, candidate_solution)
        return fault["family"] == "OK"

    def repair_routes(routes):
        # Simple repair heuristic: if a route is infeasible, try to split it
        for i, route in enumerate(routes):
            if not is_feasible([route]):
                # Try to split the route at each possible point
                for j in range(1, len(route) - 1):
                    new_routes = routes[:i] + [route[:j+1], route[j+1:]] + routes[i+1:]
                    if is_feasible(new_routes):
                        return new_routes
        return routes

    def charging_policy(instance, route):
        vehicle = instance.vehicle
        current_battery = vehicle.start_soc
        current_time = 0
        stop_states = []

        for i in range(len(route) - 1):
            current_node = instance.node_map[route[i]]
            next_node = instance.node_map[route[i + 1]]

            # Calculate energy required to travel to the next node
            energy_needed = energy_required(current_node, next_node, vehicle)

            # Check if the current battery is sufficient
            if current_battery < energy_needed:
                # Find the nearest charging station
                nearest_station = None
                min_distance = float('inf')
                for station_id in instance.station_ids:
                    station = instance.node_map[station_id]
                    dist = distance(current_node, station, vehicle)
                    if dist < min_distance:
                        min_distance = dist
                        nearest_station = station

                # If a charging station is found, recharge at it
                if nearest_station:
                    charge_decision = full_recharge(vehicle, current_battery)
                    current_time += charge_decision.duration
                    current_battery = charge_decision.battery_departure

                    # Propagate the route to the charging station
                    stop_state = propagate_route(instance, [current_node.id, nearest_station.id])[-1]
                    stop_states.append(stop_state)

                    # Update current time and battery after recharge
                    current_time = stop_state.departure_time
                    current_battery = stop_state.battery_departure

            # Travel to the next node
            current_time += travel_time(current_node, next_node, vehicle)
            current_battery -= energy_needed

            # Propagate the route to the next node
            stop_state = propagate_route(instance, [current_node.id, next_node.id])[-1]
            stop_states.append(stop_state)

            # Update current time and battery after travel
            current_time = stop_state.departure_time
            current_battery = stop_state.battery_departure

        return stop_states

    # Initial route generation
    routes = initial_routes(instance)
    
    # Repair infeasible routes
    routes = repair_routes(routes)
    
    # Ensure all routes start and end at the depot
    for i, route in enumerate(routes):
        if route[0] != instance.depot_id or route[-1] != instance.depot_id:
            routes[i] = [instance.depot_id] + route + [instance.depot_id]
    
    return {"routes": routes, "metadata": {}}