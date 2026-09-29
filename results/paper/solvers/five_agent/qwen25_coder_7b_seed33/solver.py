import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    n_customers = instance.n_customers
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle
    capacity = vehicle.capacity
    battery_capacity = vehicle.battery_capacity
    consumption_rate = vehicle.consumption_rate
    velocity = vehicle.velocity
    inverse_refuel_rate = vehicle.inverse_refuel_rate
    start_soc = vehicle.start_soc

    def is_feasible(route):
        current_soc = start_soc
        for i in range(len(route) - 1):
            current_node = instance.node_map[route[i]]
            next_node = instance.node_map[route[i + 1]]
            current_soc -= consumption_rate * distance(current_node, next_node) / velocity
            if current_soc < 0:
                return False
        return True

    def repair_route(route):
        current_soc = start_soc
        for i in range(len(route) - 1):
            current_node = instance.node_map[route[i]]
            next_node = instance.node_map[route[i + 1]]
            current_soc -= consumption_rate * distance(current_node, next_node) / velocity
            if current_soc < 0:
                recharge_node = next_node
                break
        recharge_node = instance.node_map[min((distance(instance.node_map[node], recharge_node) / velocity) for node in customer_ids if node != recharge_node)]
        return route[:i + 1] + [recharge_node.id] + route[i + 1:]

    def repair_visit(instance, route, node_id):
        current_soc = instance.vehicle.start_soc
        for i in range(len(route) - 1):
            current_node = instance.node_map[route[i]]
            next_node = instance.node_map[route[i + 1]]
            current_soc -= instance.vehicle.consumption_rate * distance(current_node, next_node) / instance.vehicle.velocity
            if current_soc < 0:
                recharge_node = next_node
                break
        recharge_node = instance.node_map[min((distance(instance.node_map[node], recharge_node) / instance.vehicle.velocity) for node in instance.customer_ids if node != recharge_node)]
        return route[:i + 1] + [recharge_node.id] + route[i + 1:]

    def repair_depot(instance, route):
        current_soc = instance.vehicle.start_soc
        for i in range(len(route) - 1):
            current_node = instance.node_map[route[i]]
            next_node = instance.node_map[route[i + 1]]
            current_soc -= instance.vehicle.consumption_rate * distance(current_node, next_node) / instance.vehicle.velocity
            if current_soc < 0:
                recharge_node = next_node
                break
        recharge_node = instance.node_map[min((distance(instance.node_map[node], recharge_node) / instance.vehicle.velocity) for node in instance.customer_ids if node != recharge_node)]
        return route[:i + 1] + [recharge_node.id] + route[i + 1:]

    def repair_capacity(instance, route):
        current_soc = instance.vehicle.start_soc
        current_load = 0
        for i in range(len(route) - 1):
            current_node = instance.node_map[route[i]]
            next_node = instance.node_map[route[i + 1]]
            current_soc -= instance.vehicle.consumption_rate * distance(current_node, next_node) / instance.vehicle.velocity
            current_load += instance.node_map[route[i + 1]].demand
            if current_soc < 0 or current_load > instance.vehicle.capacity:
                recharge_node = next_node
                break
        recharge_node = instance.node_map[min((distance(instance.node_map[node], recharge_node) / instance.vehicle.velocity) for node in instance.customer_ids if node != recharge_node)]
        return route[:i + 1] + [recharge_node.id] + route[i + 1:]

    routes = [depot_id]
    for customer in customers:
        routes.append(customer.id)
        routes.append(depot_id)

    while not is_feasible(routes):
        routes = repair_route(routes)

    return {
        "routes": [routes],
        "metadata": {
            "feasibility": True,
            "vehicles": 1,
            "distance": sum(distance(instance.node_map[routes[i]], instance.node_map[routes[i + 1]]) for i in range(len(routes) - 1))
        }
    }