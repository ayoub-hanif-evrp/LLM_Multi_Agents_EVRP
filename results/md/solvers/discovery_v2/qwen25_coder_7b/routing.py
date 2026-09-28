from evrptw_autolab.problem.physics import distance, travel_time, energy_required, propagate_route

def nearest_neighbor(instance):
    routes = []
    unvisited_customers = set(instance.customer_ids)
    current_depot = instance.depot_id

    while unvisited_customers:
        route = [current_depot]
        remaining_customers = list(unvisited_customers)

        while remaining_customers:
            nearest_customer = None
            min_distance = float('inf')

            for customer in remaining_customers:
                dist = distance(instance.node_map[current_depot], instance.node_map[customer])
                if dist < min_distance:
                    min_distance = dist
                    nearest_customer = customer

            route.append(nearest_customer)
            unvisited_customers.remove(nearest_customer)
            current_depot = nearest_customer

        route.append(current_depot)
        routes.append(route)

    return routes

def solve(instance, seed: int, time_limit_s: float):
    routes = nearest_neighbor(instance)
    metadata = {
        "vehicles": len(routes),
        "distance": sum(distance(instance.node_map[routes[i][j]], instance.node_map[routes[i][j+1]]) for i in range(len(routes)) for j in range(len(routes[i])-1))
    }
    return {"routes": routes, "metadata": metadata}