import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = list(instance.customer_ids)
    station_ids = list(instance.station_ids)
    vehicle = instance.vehicle
    
    # Initialize routes with the depot
    routes = [[depot_id]]
    
    # Shuffle customers to ensure randomness
    random.shuffle(customer_ids)
    
    for customer_id in customer_ids:
        # Find the best route to insert the customer
        best_route_index = -1
        best_insertion_index = -1
        best_cost = float('inf')
        
        for route_index, route in enumerate(routes):
            for insertion_index in range(1, len(route)):
                # Calculate the cost of inserting the customer at this position
                new_route = route[:insertion_index] + [customer_id] + route[insertion_index:]
                stops = propagate_route(instance, new_route)
                
                # Check if the route is feasible
                if all(stop.arrival_time <= stop.due_time for stop in stops):
                    # Calculate the cost (total distance)
                    cost = sum(distance(instance.node_map[new_route[i]], instance.node_map[new_route[i+1]]) for i in range(len(new_route) - 1))
                    
                    if cost < best_cost:
                        best_cost = cost
                        best_route_index = route_index
                        best_insertion_index = insertion_index
        
        # Insert the customer into the best route
        if best_route_index != -1:
            routes[best_route_index].insert(best_insertion_index, customer_id)
        else:
            # If no feasible route is found, create a new route
            routes.append([depot_id, customer_id, depot_id])
    
    # Ensure each route starts and ends at the depot
    for route in routes:
        if route[0] != depot_id:
            route.insert(0, depot_id)
        if route[-1] != depot_id:
            route.append(depot_id)
    
    # Add charging stations if necessary
    for route in routes:
        stops = propagate_route(instance, route)
        for i in range(len(stops) - 1):
            if stops[i].battery_departure < stops[i+1].battery_arrival:
                # Insert a charging station before the next node
                route.insert(i + 1, random.choice(station_ids))
                break
    
    return {"routes": routes, "metadata": {}}