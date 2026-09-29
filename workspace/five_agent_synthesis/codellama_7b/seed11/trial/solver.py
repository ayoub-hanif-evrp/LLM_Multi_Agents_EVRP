import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import EVRPTWInstance, Node, VehicleSpec, StopState, ChargeDecision

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> dict:
    random.seed(seed)

    # Initialize the vehicle
    vehicle = instance.vehicle
    vehicle.battery_capacity = vehicle.capacity
    vehicle.inverse_refuel_rate = 1 / vehicle.consumption_rate

    # Initialize the routes
    routes = []
    for customer_id in instance.customer_ids:
        route = [instance.depot_id]
        route.append(customer_id)
        routes.append(route)

    # Propagate the routes
    for route in routes:
        for i in range(1, len(route)):
            node_id = route[i]
            node = instance.node_map[node_id]
            vehicle.load = node.demand
            vehicle.battery_arrival = node.ready_time
            vehicle.battery_departure = node.due_time
            vehicle.energy_required = energy_required(node, vehicle)
            vehicle.distance_so_far = distance(node, vehicle)
            vehicle.travel_time = travel_time(node, vehicle)
            vehicle.energy_charged = full_recharge(vehicle, vehicle.battery_arrival)
            vehicle.duration = vehicle.energy_charged.duration
            vehicle.battery_departure = vehicle.battery_arrival + vehicle.duration
            vehicle.distance_so_far += vehicle.distance_so_far

    # Return the routes
    return {"routes": routes, "metadata": {"feasibility": "improve", "vehicles": "reduce"}}