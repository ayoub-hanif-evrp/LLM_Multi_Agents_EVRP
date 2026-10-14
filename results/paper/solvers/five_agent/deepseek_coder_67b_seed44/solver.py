from typing import List, Tuple

class Node:
    def __init__(self, id: str, kind: str, x: float, y: float, demand: float, ready_time: float, due_time: float, service_time: float):
        self.id = id
        self.kind = kind
        self.x = x
        self.y = y
        self.demand = demand
        self.ready_time = ready_time
        self.due_time = due_time
        self.service_time = service_time

class VehicleSpec:
    def __init__(self, capacity: float, battery_capacity: float, consumption_rate: float, velocity: float, inverse_refuel_rate: float, start_soc: float):
        self.capacity = capacity
        self.battery_capacity = battery_capacity
        self.consumption_rate = consumption_rate
        self.velocity = velocity
        self.inverse_refuel_rate = inverse_refuel_rate
        self.start_soc = start_soc

class EVRPTWInstance:
    def __init__(self, depot_id: str, customer_ids: Tuple[str, ...], n_customers: int, station_ids: Tuple[str, ...], customers: Tuple[Node, ...], stations: Tuple[Node, ...], depot: Node, vehicle: VehicleSpec):
        self.depot_id = depot_id
        self.customer_ids = customer_ids
        self.n_customers = n_customers
        self.station_ids = station_ids
        self.customers = customers
        self.stations = stations
        self.depot = depot
        self.vehicle = vehicle

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> dict:
    # Initialize the random seed
    import random
    random.seed(seed)

    # Create a list of customer IDs
    customer_ids = list(instance.customer_ids)

    # Initialize the routes
    routes = []

    # While there are still customers to visit
    while customer_ids:
        # Create a new route with the depot at the start and end
        route = [instance.depot_id]

        # Choose a random customer to start with
        current_customer = random.choice(customer_ids)

        # Add the customer to the route and remove it from the list of unvisited customers
        route.append(current_customer)
        customer_ids.remove(current_customer)

        # While there are still customers to visit
        while customer_ids:
            # Find the customer that is closest to the current location
            closest_customer = min(customer_ids, key=lambda customer: distance(instance.node_map[current_customer], instance.node_map[customer]))

            # Add the closest customer to the route and remove it from the list of unvisited customers
            route.append(closest_customer)
            customer_ids.remove(closest_customer)

            # Update the current location to the new customer
            current_customer = closest_customer

        # Add the route to the list of routes
        routes.append(route)

    # Return the routes
    return {"routes": routes, "metadata": {}}