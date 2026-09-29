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
    
    def generate_initial_routes():
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
            
            travel = travel_time(instance.node_map[current_route[-1]], customer, instance.vehicle)
            energy = energy_required(instance.node_map[current_route[-1]], customer, instance.vehicle)
            
            if current_time + travel > customer.ready_time:
                current_time += travel
            else:
                current_time = customer.ready_time
            
            if current_battery - energy < 0:
                charge_decision = full_recharge(instance.vehicle, current_battery)
                current_time += charge_decision.duration
                current_battery = charge_decision.battery_departure
            
            current_route.append(customer_id)
            current_load += customer.demand
            current_battery -= energy
            current_time += customer.service_time
        
        if current_route:
            routes.append(current_route + [instance.depot_id])
        
        return routes
    
    def local_search(routes):
        # Simple local search: try to swap two consecutive customers in a route
        improved = True
        while improved:
            improved = False
            for i in range(len(routes)):
                route = routes[i]
                for j in range(1, len(route) - 2):
                    for k in range(j + 1, len(route) - 1):
                        new_route = route[:j] + [route[k], route[j]] + route[k+1:]
                        new_routes = [r if r != route else new_route for r in routes]
                        if is_feasible(new_routes):
                            routes = new_routes
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
        return routes
    
    def ensure_all_customers_visited(routes):
        visited_customers = set()
        for route in routes:
            for node_id in route:
                if node_id in instance.customer_ids:
                    visited_customers.add(node_id)
        if len(visited_customers) != instance.n_customers:
            missing_customers = set(instance.customer_ids) - visited_customers
            for customer_id in missing_customers:
                # Add a new route with the missing customer
                routes.append([instance.depot_id, customer_id, instance.depot_id])
        return routes
    
    initial_routes = generate_initial_routes()
    initial_routes = ensure_all_customers_visited(initial_routes)
    if not is_feasible(initial_routes):
        return {"routes": [], "metadata": {}}
    
    final_routes = local_search(initial_routes)
    
    return {"routes": final_routes, "metadata": {}}