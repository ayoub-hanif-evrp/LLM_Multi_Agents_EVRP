import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import EVRPTWInstance, Node, VehicleSpec, StopState, ChargeDecision

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> dict:
    # Initialize the random seed
    random.seed(seed)

    # Initialize the vehicle and its battery
    vehicle = instance.vehicle
    battery_capacity = vehicle.battery_capacity
    battery_departure = vehicle.start_soc

    # Initialize the routes
    routes = []

    # Iterate over the customers
    for customer_id in instance.customer_ids:
        # Get the customer node
        customer = instance.node_map[customer_id]

        # Get the arrival time at the customer
        arrival_time = customer.ready_time

        # Get the service time at the customer
        service_time = customer.service_time

        # Get the load at the customer
        load = customer.demand

        # Propagate the route from the previous customer to the current customer
        previous_stop = routes[-1][-1] if len(routes) > 0 else instance.depot_id
        previous_stop_state = propagate_route(instance, previous_stop)
        previous_stop_state.load += load
        previous_stop_state.distance_so_far += distance(previous_stop, customer)
        previous_stop_state.energy_charged += energy_required(previous_stop, customer, vehicle)
        previous_stop_state.battery_departure = full_recharge(vehicle, previous_stop_state.battery_departure).battery_departure

        # Add the current customer to the route
        routes[-1].append(customer_id)

        # Update the arrival time at the current customer
        arrival_time += service_time

        # Update the battery level at the current customer
        battery_departure = full_recharge(vehicle, battery_departure).battery_departure

    # Return the routes
    return {"routes": routes, "metadata": {"time_limit_s": time_limit_s, "seed": seed}}