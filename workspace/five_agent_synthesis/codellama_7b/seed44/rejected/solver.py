import random

from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import EVRPTWInstance, Node, VehicleSpec, StopState, ChargeDecision


def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> dict:
    """
    Solve the EVRPTW problem using a routing, charging, search, and critic role.
    """
    # Set the random seed for reproducibility
    random.seed(seed)

    # Initialize the routing and charging components
    routing = Routing(instance)
    charging = Charging(instance)

    # Initialize the search control
    search = SearchControl(instance, routing, charging)

    # Run the search
    search.run(time_limit_s)

    # Return the final solution
    return search.solution


class Routing:
    """
    The routing component of the EVRPTW solver.
    """

    def __init__(self, instance: EVRPTWInstance):
        self.instance = instance
        self.routes = []

    def run(self, time_limit_s: float):
        """
        Run the routing component of the EVRPTW solver.
        """
        # Initialize the routes
        self.routes = [[] for _ in range(self.instance.n_vehicles)]

        # Iterate over the customers
        for customer_id in self.instance.customer_ids:
            # Get the customer node
            customer = self.instance.node_map[customer_id]

            # Find the closest vehicle
            closest_vehicle = None
            closest_distance = float("inf")
            for vehicle_id in range(self.instance.n_vehicles):
                vehicle = self.instance.vehicle
                distance_to_vehicle = distance(vehicle.position, customer.position)
                if distance_to_vehicle < closest_distance:
                    closest_distance = distance_to_vehicle
                    closest_vehicle = vehicle_id

            # Add the customer to the route
            self.routes[closest_vehicle].append(customer_id)

        # Return the routes
        return self.routes


class Charging:
    """
    The charging component of the EVRPTW solver.
    """

    def __init__(self, instance: EVRPTWInstance):
        self.instance = instance
        self.routes = []

    def run(self, time_limit_s: float):
        """
        Run the charging component of the EVRPTW solver.
        """
        # Initialize the routes
        self.routes = [[] for _ in range(self.instance.n_vehicles)]

        # Iterate over the customers
        for customer_id in self.instance.customer_ids:
            # Get the customer node
            customer = self.instance.node_map[customer_id]

            # Find the closest vehicle
            closest_vehicle = None
            closest_distance = float("inf")
            for vehicle_id in range(self.instance.n_vehicles):
                vehicle = self.instance.vehicle
                distance_to_vehicle = distance(vehicle.position, customer.position)
                if distance_to_vehicle < closest_distance:
                    closest_distance = distance_to_vehicle
                    closest_vehicle = vehicle_id

            # Add the customer to the route
            self.routes[closest_vehicle].append(customer_id)

        # Return the routes
        return self.routes


class SearchControl:
    """
    The search control component of the EVRPTW solver.
    """

    def __init__(self, instance: EVRPTWInstance, routing: Routing, charging: Charging):
        self.instance = instance
        self.routing = routing
        self.charging = charging
        self.solution = None

    def run(self, time_limit_s: float):
        """
        Run the search control component of the EVRPTW solver.
        """
        # Initialize the solution
        self.solution = {"routes": [], "metadata": {}}

        # Run the search
        while time_limit_s > 0:
            # Get the next route
            route = self.routing.run(time_limit_s)

            # Get the next charging route
            charging_route = self.charging.run(time_limit_s)

            # Add the routes to the solution
            self.solution["routes"].append(route)
            self.solution["routes"].append(charging_route)

            # Update the time limit
            time_limit_s -= 1

        # Return the solution
        return self.solution