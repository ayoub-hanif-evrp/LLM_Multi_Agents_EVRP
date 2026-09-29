import random
import time
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = list(instance.customer_ids)
    n_customers = instance.n_customers
    customers = instance.customers
    vehicle = instance.vehicle
    depot = instance.depot
    
    # Initialize routes
    routes = [[] for _ in range(n_customers)]
    
    # Function to add a customer to a route
    def add_customer_to_route(route, customer_id):
        route.append(customer_id)
    
    # Function to calculate the total distance of a route
    def total_distance(route):
        total = 0
        for i in range(len(route) - 1):
            total += distance(instance.node_map[route[i]], instance.node_map[route[i + 1]])
        return total
    
    # Function to calculate the total energy consumption of a route
    def total_energy_consumption(route):
        total = 0
        for i in range(len(route) - 1):
            total += energy_required(instance.node_map[route[i]], instance.node_map[route[i + 1]], vehicle)
        return total
    
    # Function to calculate the total number of vehicles used
    def total_vehicles(routes):
        return len(routes)
    
    # Function to check if a route is feasible
    def is_route_feasible(route):
        current_load = 0
        current_battery = vehicle.start_soc
        for customer_id in route:
            customer = instance.node_map[customer_id]
            if current_load + customer.demand > vehicle.capacity:
                return False
            if current_battery < energy_required(depot, customer, vehicle):
                return False
            current_load += customer.demand
            current_battery -= energy_required(depot, customer, vehicle)
        return True
    
    # Function to repair a route
    def repair_route(route):
        current_load = 0
        current_battery = vehicle.start_soc
        new_route = [instance.depot_id]
        for customer_id in route:
            customer = instance.node_map[customer_id]
            if current_load + customer.demand > instance.vehicle.capacity:
                new_route.append(instance.depot_id)
                current_load = customer.demand
                current_battery = instance.vehicle.start_soc - energy_required(instance.depot, customer, instance.vehicle)
            elif current_battery < energy_required(instance.depot, customer, instance.vehicle):
                new_route.append(instance.depot_id)
                current_load = customer.demand
                current_battery = instance.vehicle.start_soc - energy_required(instance.depot, customer, instance.vehicle)
            else:
                new_route.append(customer_id)
                current_load += customer.demand
                current_battery -= energy_required(depot, customer, instance.vehicle)
        new_route.append(instance.depot_id)
        return new_route
    
    # Main loop
    start_time = time.time()
    while time.time() - start_time < time_limit_s:
        for i in range(n_customers):
            if not routes[i]:
                customer_id = random.choice(customer_ids)
                if is_route_feasible([depot_id, customer_id, depot_id]):
                    routes[i].append(depot_id)
                    routes[i].append(customer_id)
                    routes[i].append(depot_id)
                    customer_ids.remove(customer_id)
    
    # Repair infeasible routes
    for i in range(n_customers):
        if not is_route_feasible(routes[i]):
            routes[i] = repair_route(routes[i])
    
    # Return the solution
    return {"routes": routes, "metadata": {"total_distance": sum(total_distance(route) for route in routes), "total_vehicles": total_vehicles(routes)}}