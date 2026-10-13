from evrptw_autolab.problem.physics import distance, energy_required

def solve(instance, seed: int, time_limit_s: float):
    # Set the random seed
    import random
    random.seed(seed)

    # Initialize the solution
    solution = {"routes": [], "metadata": {}}

    # TODO: Implement your solution here
    # For example, we can start by adding the depot to each route
    for _ in range(instance.n_customers):
        solution["routes"].append([instance.depot_id])

    # Then we can add the customers to the routes in a random order
    for customer_id in random.sample(instance.customer_ids, len(instance.customer_ids)):
        # Find the route with the shortest total distance
        _, shortest_route = min(
            (sum(distance(instance.node_map[route[i]], instance.node_map[route[i+1]])
                 for i in range(len(route) - 1)) +
             energy_required(instance.node_map[route[-1]], instance.node_map[customer_id], instance.vehicle),
             route)
            for route in solution["routes"])

        # Add the customer to the route
        shortest_route.append(customer_id)

    # Finally, add the depot back to the end of each route
    for route in solution["routes"]:
        route.append(instance.depot_id)

    return solution