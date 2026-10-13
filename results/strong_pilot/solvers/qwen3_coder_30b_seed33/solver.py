import random
import time
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    import random
    import time
    from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
    
    random.seed(seed)
    start_time = time.time()
    
    # Initial construction: assign customers to routes greedily
    customers = list(instance.customer_ids)
    random.shuffle(customers)
    
    routes = []
    visited_customers = set()
    
    while len(visited_customers) < instance.n_customers:
        if time.time() - start_time > time_limit_s:
            break
            
        route = [instance.depot_id]
        current_load = 0.0
        current_battery = instance.vehicle.start_soc
        current_time = 0.0
        
        # Try to add customers to the current route
        i = 0
        while i < len(customers):
            if time.time() - start_time > time_limit_s:
                break
                
            customer_id = customers[i]
            if customer_id in visited_customers:
                i += 1
                continue
                
            customer = instance.node_map[customer_id]
            
            # Check capacity constraint
            if current_load + customer.demand > instance.vehicle.capacity:
                i += 1
                continue
            
            # Build a temporary route to check feasibility
            temp_route = route + [customer_id]
            try:
                states = propagate_route(instance, temp_route)
                last_state = states[-1]
                
                # Check if we can reach the customer with current battery
                if last_state.battery_arrival < 0:
                    i += 1
                    continue
                
                # Check time window constraint
                arrival_time = last_state.arrival_time
                if arrival_time > customer.due_time:
                    i += 1
                    continue
            except Exception:
                i += 1
                continue
            
            # Add the customer to route
            route.append(customer_id)
            visited_customers.add(customer_id)
            
            # Update state
            current_load += customer.demand
            current_battery = last_state.battery_departure
            current_time = last_state.departure_time
            
            i += 1
            
        # Return to depot
        if len(route) > 1:
            temp_route = route + [instance.depot_id]
            try:
                states = propagate_route(instance, temp_route)
                last_state = states[-1]
                
                # If we can't reach the depot with current battery, try to recharge
                if last_state.battery_arrival < 0:
                    # Find a suitable station to recharge before returning to depot
                    best_station = None
                    min_energy_needed = float('inf')
                    
                    for station_id in instance.station_ids:
                        temp_route_with_station = route[:-1] + [station_id, instance.depot_id]
                        try:
                            states_with_station = propagate_route(instance, temp_route_with_station)
                            last_state = states_with_station[-1]
                            if last_state.battery_arrival >= 0:
                                # Check if we can reach the station and return to depot
                                charge_decision = full_recharge(instance.vehicle, states_with_station[-2].battery_departure)
                                battery_after_charge = charge_decision.battery_departure
                                
                                energy_req_to_depot = energy_required(instance.node_map[station_id], instance.node_map[instance.depot_id], instance.vehicle)
                                if battery_after_charge - energy_req_to_depot >= 0:
                                    if min_energy_needed > energy_required(instance.node_map[route[-1]], instance.node_map[station_id], instance.vehicle):
                                        min_energy_needed = energy_required(instance.node_map[route[-1]], instance.node_map[station_id], instance.vehicle)
                                        best_station = station_id
                        except Exception:
                            continue
                    
                    # If we found a suitable station, recharge there and then return to depot
                    if best_station is not None:
                        route.insert(-1, best_station)
                        route.append(instance.depot_id)
                        routes.append(route)
                    else:
                        # If we can't return to depot even after charging, drop this route
                        pass
                else:
                    # We have enough battery to return to depot directly
                    route.append(instance.depot_id)
                    routes.append(route)
            except Exception:
                pass
        else:
            # No customers added to this route
            pass
    
    # Final validation and cleanup
    all_customers = set()
    for route in routes:
        for node_id in route:
            if node_id == instance.depot_id:
                continue
            elif node_id in instance.customer_ids:
                all_customers.add(node_id)
    
    # Ensure all customers are visited exactly once
    assert len(all_customers) == instance.n_customers, "Not all customers visited or some visited multiple times"
    
    # Validate routes
    for route in routes:
        assert route[0] == instance.depot_id and route[-1] == instance.depot_id, "Route must start and end at depot"
        assert len(route) >= 2, "Route must have at least depot and one customer"
        
        # Check that no internal depots
        for i in range(1, len(route)-1):
            assert route[i] != instance.depot_id, "No internal depots allowed"
    
    return {"routes": routes, "metadata": {}}



