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
        remaining_customers = list(instance.customer_ids)
        while remaining_customers:
            route = [instance.depot_id]
            current_node = instance.depot
            current_load = 0
            current_battery = instance.vehicle.start_soc
            
            while remaining_customers:
                next_customer = None
                for customer_id in remaining_customers:
                    customer = instance.node_map[customer_id]
                    if customer.demand + current_load <= instance.vehicle.capacity:
                        if current_battery - energy_required(current_node, customer, instance.vehicle) >= 0:
                            next_customer = customer
                            break
                
                if next_customer:
                    route.append(next_customer.id)
                    current_load += next_customer.demand
                    current_battery -= energy_required(current_node, next_customer, instance.vehicle)
                    current_node = next_customer
                    remaining_customers.remove(next_customer.id)
                else:
                    break
            
            route.append(instance.depot_id)
            routes.append(route)
        
        return routes
    
    def repair_routes(routes):
        # Basic repair logic: if a route is infeasible, try to split it
        for i, route in enumerate(routes):
            candidate = CandidateSolution(routes=[route])
            fault = first_fault(instance, candidate)
            if fault["family"] != "OK":
                # Split the route at the fault point
                split_index = fault["route_index"]
                routes[i] = route[:split_index + 1]
                routes.append(route[split_index + 1:])
                break
        
        return routes
    
    def local_search(routes):
        # Simple local search: try swapping two customers in different routes
        for _ in range(100):
            if len(routes) < 2:
                continue
            i, j = random.sample(range(len(routes)), 2)
            if len(routes[i]) > 2 and len(routes[j]) > 2:
                # Swap two customers
                customer_i = random.choice(routes[i][1:-1])
                customer_j = random.choice(routes[j][1:-1])
                
                routes[i].remove(customer_i)
                routes[j].remove(customer_j)
                
                routes[i].insert(random.randint(1, len(routes[i]) - 1), customer_j)
                routes[j].insert(random.randint(1, len(routes[j]) - 1), customer_i)
                
                if is_feasible(routes):
                    return routes
        
        return routes
    
    # Generate initial routes
    routes = generate_initial_routes()
    
    # Repair initial routes
    routes = repair_routes(routes)
    
    # Perform local search
    routes = local_search(routes)
    
    # Ensure all customers are visited
    all_customers = set(instance.customer_ids)
    visited_customers = set()
    for route in routes:
        visited_customers.update(route[1:-1])
    
    if all_customers != visited_customers:
        # If any customer is missing, add a new route for them
        missing_customers = all_customers - visited_customers
        for customer_id in missing_customers:
            routes.append([instance.depot_id, customer_id, instance.depot_id])
    
    # Ensure feasibility
    while not is_feasible(routes):
        routes = repair_routes(routes)
        routes = local_search(routes)
    
    return {"routes": routes, "metadata": {}}