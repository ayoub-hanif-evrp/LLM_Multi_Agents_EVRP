import random
from typing import List, Dict
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import Node, VehicleSpec, CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    def is_feasible(route):
        stops = propagate_route(instance, route)
        for stop in stops:
            if stop.battery_departure < 0:
                return False
        return True

    def construct_initial_routes():
        routes = []
        unvisited_customers = list(instance.customer_ids)
        while unvisited_customers:
            route = [instance.depot_id]
            current_node = instance.depot
            remaining_capacity = instance.vehicle.capacity
            remaining_battery = instance.vehicle.start_soc * instance.vehicle.battery_capacity
            
            while unvisited_customers:
                next_customer = None
                min_distance = float('inf')
                
                for customer_id in unvisited_customers:
                    customer = instance.node_map[customer_id]
                    dist = distance(current_node, customer)
                    if dist < min_distance and customer.demand <= remaining_capacity and energy_required(current_node, customer, instance.vehicle) <= remaining_battery:
                        min_distance = dist
                        next_customer = customer_id
                
                if next_customer:
                    route.append(next_customer)
                    unvisited_customers.remove(next_customer)
                    current_node = customer
                    remaining_capacity -= customer.demand
                    remaining_battery -= energy_required(current_node, instance.depot, instance.vehicle)
                else:
                    break
            
            route.append(instance.depot_id)
            routes.append(route)
        
        return routes

    def optimize_routes(routes):
        # Simple optimization: try to insert stations if needed
        for route in routes:
            stops = propagate_route(instance, route)
            for i in range(len(stops) - 1):
                if stops[i].battery_departure < 0:
                    # Insert a station before the node that causes the battery to run out
                    for station_id in instance.station_ids:
                        new_route = route[:i] + [station_id] + route[i:]
                        if is_feasible(new_route):
                            route = new_route
                            break
        
        return routes

    initial_routes = construct_initial_routes()
    optimized_routes = optimize_routes(initial_routes)

    return {
        "routes": optimized_routes,
        "metadata": {
            "seed": seed,
            "time_limit_s": time_limit_s,
            "num_routes": len(optimized_routes),
            "total_distance": sum(distance(instance.node_map[route[i]], instance.node_map[route[i+1]]) for route in optimized_routes for i in range(len(route) - 1))
        }
    }