from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import CandidateSolution
import random

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)

    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle

    # Initialize routes
    routes = [[depot_id]]

    # Assign customers to routes
    for customer_id in customer_ids:
        customer = instance.node_map[customer_id]
        best_route_index = None
        best_route_cost = float('inf')

        for i, route in enumerate(routes):
            if len(route) == 1:
                route_cost = distance(instance.node_map[route[0]], customer) + distance(customer, instance.node_map[depot_id])
            else:
                route_cost = distance(instance.node_map[route[-2]], customer) + distance(customer, instance.node_map[route[-1]])

            if route_cost < best_route_cost:
                best_route_index = i
                best_route_cost = route_cost

        if best_route_index is not None:
            routes[best_route_index].append(customer_id)
        else:
            routes.append([depot_id, customer_id, depot_id])

    # Add depot to the end of each route
    for route in routes:
        route.append(depot_id)

    # Convert routes to list of string ids
    routes = [route for route in routes]

    # Create candidate solution
    candidate_solution = CandidateSolution(routes=routes)

    # Check feasibility
    from evrptw_autolab.problem.evaluator import first_fault
    packet = first_fault(instance, candidate_solution)

    if packet["family"] != "OK":
        print(f"First fault detected: {packet}")

    # Repair battery issues
    for i, route in enumerate(routes):
        if i == 0:
            continue  # Skip depot route
        for j in range(1, len(route) - 1):
            node_id = route[j]
            node = instance.node_map[node_id]
            if node.kind == "customer":
                state = propagate_route(instance, route[:j + 1])[-1]
                if state.battery_arrival < 0:
                    recharge_decision = full_recharge(vehicle, state.battery_arrival)
                    state.energy_charged = recharge_decision.energy_charged
                    state.battery_departure = recharge_decision.battery_departure

    return {"routes": routes, "metadata": {}}