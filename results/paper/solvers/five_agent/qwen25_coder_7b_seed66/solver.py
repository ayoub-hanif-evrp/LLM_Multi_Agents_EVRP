import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)

    # Initialize variables
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    n_customers = instance.n_customers
    customers = instance.customers
    vehicle = instance.vehicle

    # Helper function to check if a route is feasible
    def is_route_feasible(route):
        current_time = 0
        current_load = 0
        current_battery = vehicle.start_soc
        for node_id in route:
            if node_id == depot_id:
                continue
            node = instance.node_map[node_id]
            if current_time < node.ready_time:
                current_time = node.ready_time
            travel_time_to_node = travel_time(instance.node_map[route[route.index(node_id) - 1]], node, vehicle)
            current_time += travel_time_to_node
            current_load += node.demand
            if current_load > vehicle.capacity:
                return False
            energy_required_to_node = energy_required(instance.node_map[route[route.index(node_id) - 1]], node, vehicle)
            if current_battery < energy_required_to_node:
                return False
            current_battery -= energy_required_to_node
            if node.kind == 'station':
                charge_decision = full_recharge(vehicle, current_battery)
                current_battery = charge_decision.battery_departure
        return True

    # Main optimization loop
    routes = []
    while len(routes) < n_customers:
        # Construct a route
        route = [depot_id]
        current_load = 0
        current_battery = vehicle.start_soc
        for customer_id in customer_ids:
            if current_load + instance.node_map[customer_id].demand > vehicle.capacity:
                break
            if current_battery < energy_required(instance.node_map[route[-1]], instance.node_map[customer_id], vehicle):
                break
            route.append(customer_id)
            current_load += instance.node_map[customer_id].demand
            energy_required_to_customer = energy_required(instance.node_map[route[-2]], instance.node_map[customer_id], vehicle)
            current_battery -= energy_required_to_customer
            if instance.node_map[customer_id].kind == 'station':
                charge_decision = full_recharge(vehicle, current_battery)
                current_battery = charge_decision.battery_departure
        route.append(depot_id)
        routes.append(route)

    # Filter out infeasible routes
    feasible_routes = [route for route in routes if is_route_feasible(route)]

    # Return the solution
    return {"routes": feasible_routes, "metadata": {"vehicles": len(feasible_routes)}}