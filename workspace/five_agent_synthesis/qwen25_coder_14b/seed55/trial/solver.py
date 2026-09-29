import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    
    # Initialize routes with each customer in its own route starting and ending at the depot
    routes = [[instance.depot_id, customer_id, instance.depot_id] for customer_id in instance.customer_ids]
    
    # Function to evaluate the feasibility of a solution
    def evaluate_solution(routes):
        candidate = CandidateSolution(routes=routes)
        fault = first_fault(instance, candidate)
        if fault["family"] != "OK":
            return float('inf'), fault["family"]
        
        # Calculate the total distance
        total_distance = sum(distance(instance.node_map[routes[i][j]], instance.node_map[routes[i][j+1]]) for i in range(len(routes)) for j in range(len(routes[i]) - 1))
        
        return total_distance, "OK"
    
    # Local search to improve the solution
    def local_search(routes, time_limit_s):
        start_time = time.time()
        while time.time() - start_time < time_limit_s:
            # Select a random route to modify
            route_index = random.randint(0, len(routes) - 1)
            route = routes[route_index]
            
            # Select two random positions in the route to swap
            pos1, pos2 = random.sample(range(1, len(route) - 1), 2)
            
            # Swap the positions
            route[pos1], route[pos2] = route[pos2], route[pos1]
            
            # Evaluate the new solution
            new_distance, fault = evaluate_solution(routes)
            if fault == "OK":
                return routes, new_distance
        return routes, evaluate_solution(routes)[0]
    
    # Main loop to improve the solution
    best_routes, best_distance = routes, evaluate_solution(routes)[0]
    for _ in range(10):  # Number of restarts
        routes, distance = local_search(routes, time_limit_s / 10)
        if distance < best_distance:
            best_routes, best_distance = routes, distance
    
    return {"routes": best_routes, "metadata": {"best_distance": best_distance}}