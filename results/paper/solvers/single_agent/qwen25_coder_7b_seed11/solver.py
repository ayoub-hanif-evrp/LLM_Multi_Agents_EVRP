from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    vehicle = instance.vehicle
    
    # Initialize routes with the depot
    routes = [[depot_id] for _ in range(len(customers))]
    
    # Assign customers to routes randomly
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        route_index = random.randint(0, len(routes) - 1)
        routes[route_index].append(customer_id)
        routes[route_index].append(depot_id)
    
    # Convert routes to list of node ids
    routes = [route[1:-1] for route in routes]  # Remove depot from the start and end of each route
    
    # Create a candidate solution
    candidate_solution = CandidateSolution(routes=routes)
    
    # Check the feasibility of the solution
    packet = first_fault(instance, candidate_solution)
    
    # If the solution is not feasible, fix the first fault
    if packet["family"] != "OK":
        # Implement a simple repair strategy (e.g., swap customers between routes)
        if packet["family"] == "CAPACITY":
            # Swap customers between routes to fix capacity violation
            route_index = packet["route_index"]
            customer_id = packet["node_id"]
            customer = instance.node_map[customer_id]
            current_route = routes[route_index]
            current_route.remove(customer_id)
            current_route.remove(depot_id)
            
            # Find another route that can accommodate the customer
            for i in range(len(routes)):
                if i != route_index:
                    other_route = routes[i]
                    if len(other_route) < 2 * len(customers) + 2 and energy_required(other_route[-1], customer, vehicle) + energy_required(customer, depot_id, vehicle) <= vehicle.capacity:
                        other_route.append(customer_id)
                        other_route.append(depot_id)
                        break
            
            # Add the customer back to the original route
            current_route.append(customer_id)
            current_route.append(depot_id)
        
        # Re-check the feasibility after repair
        packet = first_fault(instance, candidate_solution)
    
    # Return the solution
    return {"routes": routes, "metadata": {}}