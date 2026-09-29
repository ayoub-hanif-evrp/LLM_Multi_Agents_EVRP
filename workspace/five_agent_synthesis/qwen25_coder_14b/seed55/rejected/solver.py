import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with depot at the start and end
    routes = [[instance.depot_id] for _ in range(instance.vehicle.capacity)]
    
    # Assign customers to routes
    customer_list = list(instance.customer_ids)
    random.shuffle(customer_list)
    
    for customer_id in customer_list:
        # Choose a random route to add the customer
        route_index = random.randint(0, len(routes) - 1)
        routes[route_index].insert(-1, customer_id)
    
    # Ensure each route ends at the depot
    for route in routes:
        if route[-1] != instance.depot_id:
            route.append(instance.depot_id)
    
    # Check for feasibility
    candidate_solution = CandidateSolution(routes=routes)
    fault = first_fault(instance, candidate_solution)
    
    if fault["family"] != "OK":
        # If there's a fault, try to fix it
        if fault["family"] == "BATTERY":
            # Implement a simple charging strategy
            for route in routes:
                # Propagate the route to get stop states
                stop_states = propagate_route(instance, route)
                
                # Check if the route is feasible
                for i in range(len(stop_states) - 1):
                    if stop_states[i].battery_arrival < 0:
                        # If battery is depleted, recharge at the depot
                        route.insert(i + 1, instance.depot_id)
                        stop_states = propagate_route(instance, route)
    
    # Return the final routes
    return {"routes": routes, "metadata": {}}