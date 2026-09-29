from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
import random
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with the depot
    routes = [[instance.depot_id]]
    
    # Function to add a customer to a route
    def add_customer_to_route(route, customer_id):
        route.append(customer_id)
        route.append(instance.depot_id)
    
    # Add customers to routes
    for customer_id in instance.customer_ids:
        add_customer_to_route(routes[0], customer_id)
    
    # Function to check if a route is feasible
    def is_route_feasible(route):
        state = propagate_route(instance, route)
        for node_id, state in zip(route, state):
            node = instance.node_map[node_id]
            if state.battery_arrival < 0:
                return False
            if node_id in instance.customer_ids and state.service_start > node.due_time:
                return False
            if node_id == instance.depot_id and state.arrival_time > node.due_time:
                return False
        return True
    
    # Check if the initial solution is feasible
    if not is_route_feasible(routes[0]):
        # If not feasible, try to fix the first fault
        packet = first_fault(instance, CandidateSolution(routes=routes))
        if packet["family"] == "CHARGE_POLICY":
            # Full recharge at the depot
            routes[0][1] = instance.depot_id
            state = propagate_route(instance, routes[0])
            routes[0][1] = instance.customer_ids[0]
            state = propagate_route(instance, routes[0])
            routes[0][1] = instance.depot_id
        elif packet["family"] == "BATTERY":
            # Full recharge at the depot
            routes[0][1] = instance.depot_id
            state = propagate_route(instance, routes[0])
            routes[0][1] = instance.customer_ids[0]
            state = propagate_route(instance, routes[0])
            routes[0][1] = instance.depot_id
        elif packet["family"] == "WINDOW":
            # Adjust the route to respect time windows
            for i in range(1, len(routes[0]) - 1):
                node_id = routes[0][i]
                node = instance.node_map[node_id]
                if state.service_start > node.due_time:
                    routes[0][i] = instance.depot_id
                    state = propagate_route(instance, routes[0])
                    routes[0][i] = node_id
                    state = propagate_route(instance, routes[0])
    
    # Return the solution
    return {
        "routes": routes,
        "metadata": {}
    }