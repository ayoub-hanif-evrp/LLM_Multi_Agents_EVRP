import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Precompute all distances for efficiency
    dist_cache = {}
    nodes = [instance.depot] + list(instance.customers) + list(instance.stations)
    for a in nodes:
        for b in nodes:
            dist_cache[(a.id, b.id)] = distance(a, b)

    def get_distance(a_id, b_id):
        return dist_cache.get((a_id, b_id), float('inf'))

    def build_routes(instance, unvisited_customers):
        routes = []
        while unvisited_customers:
            route = [instance.depot_id]
            current_load = 0
            current_battery = instance.vehicle.start_soc
            current_time = 0.0
            current_node_id = instance.depot_id
            
            # Build a single route until no more customers can be served
            while True:
                best_customer = None
                min_cost = float('inf')
                
                for cust_id in list(unvisited_customers):
                    customer = instance.node_map[cust_id]
                    
                    # Check if we can reach this customer within time window
                    travel_t = travel_time(instance.node_map[current_node_id], customer, instance.vehicle)
                    arrival_time = current_time + travel_t
                    
                    if arrival_time > customer.due_time:
                        continue  # Cannot serve this customer in time

                    # Check capacity constraint
                    if current_load + customer.demand > instance.vehicle.capacity:
                        continue  # Not enough capacity

                    # Check battery constraint
                    energy_needed = energy_required(instance.node_map[current_node_id], customer, instance.vehicle)
                    
                    if current_battery < energy_needed:
                        # Try to recharge at a station before visiting this customer
                        best_station = None
                        min_station_dist = float('inf')
                        for station_id in instance.station_ids:
                            station = instance.node_map[station_id]
                            dist_to_station = get_distance(current_node_id, station_id)
                            dist_to_cust = get_distance(station_id, cust_id)
                            total_dist = dist_to_station + dist_to_cust
                            if total_dist < min_station_dist:
                                min_station_dist = total_dist
                                best_station = station_id

                        if not best_station:
                            continue  # No suitable station found

                        # Check if we can reach the station and then customer
                        energy_to_station = energy_required(instance.node_map[current_node_id], instance.node_map[best_station], instance.vehicle)
                        if current_battery < energy_to_station:
                            continue  # Cannot reach station

                        # Recharge at the best station and then proceed to customer
                        station = instance.node_map[best_station]
                        charge_decision = full_recharge(instance.vehicle, current_battery)
                        new_battery = charge_decision.battery_departure
                        
                        # Check if we can reach customer after recharging
                        energy_to_cust = energy_required(station, customer, instance.vehicle)
                        if new_battery < energy_to_cust:
                            continue  # Even with charging, not enough battery

                        # Add station to route and update state
                        route.append(best_station)
                        current_battery = new_battery
                        current_time += travel_t + charge_decision.duration
                        current_node_id = best_station
                    
                    # Now we can visit the customer
                    energy_needed = energy_required(instance.node_map[current_node_id], customer, instance.vehicle)
                    if current_battery < energy_needed:
                        continue  # Not enough battery even after charging

                    # Compute cost (distance + time penalty for late arrival)
                    service_start = max(current_time + travel_t, customer.ready_time)
                    departure_time = service_start + customer.service_time
                    battery_after_service = current_battery - energy_needed
                    
                    if battery_after_service < 0:
                        continue  # Battery depleted

                    # Cost function: Euclidean distance + time window violation penalty
                    cost = get_distance(current_node_id, cust_id) + (max(0, arrival_time - customer.due_time) * 10)
                    
                    if cost < min_cost:
                        min_cost = cost
                        best_customer = cust_id

                if not best_customer:
                    # No more customers can be served in this route; return to depot
                    travel_t = travel_time(instance.node_map[current_node_id], instance.depot, instance.vehicle)
                    arrival_at_depot = current_time + travel_t
                    route.append(instance.depot_id)
                    break

                customer = instance.node_map[best_customer]
                travel_t = travel_time(instance.node_map[current_node_id], customer, instance.vehicle)
                arrival_time = current_time + travel_t
                
                # Update state
                service_start = max(arrival_time, customer.ready_time)
                departure_time = service_start + customer.service_time
                energy_used = energy_required(instance.node_map[current_node_id], customer, instance.vehicle)
                
                route.append(best_customer)
                current_battery -= energy_used
                current_load += customer.demand
                current_time = departure_time
                current_node_id = best_customer
                
                unvisited_customers.remove(best_customer)

            routes.append(route)
        return routes
    
    # Initialize
    customers = list(instance.customer_ids)
    routes = build_routes(instance, set(customers))

    # Final validation
    all_customers_visited = set()
    for r in routes:
        for node_id in r:
            if node_id == instance.depot_id:
                continue
            if node_id in instance.customer_ids:
                all_customers_visited.add(node_id)
    
    if len(all_customers_visited) != instance.n_customers:
        raise RuntimeError("Not all customers were visited")

    # Validate route structure
    for r in routes:
        if r[0] != instance.depot_id or r[-1] != instance.depot_id:
            raise RuntimeError("Route must start and end at depot")
        if len(r) < 2:
            raise RuntimeError("Route must have at least depot and one customer")

    return {"routes": routes, "metadata": {}}

