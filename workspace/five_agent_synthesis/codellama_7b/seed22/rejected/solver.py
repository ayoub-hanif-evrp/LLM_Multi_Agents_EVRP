import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import EVRPTWInstance, Node, VehicleSpec, StopState, ChargeDecision

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> dict:
    """
    Solve the EVRPTW instance using a routing-based architecture with charging and search components, and a critic to evaluate the solution's feasibility and distance.

    Args:
        instance: The EVRPTW instance to solve.
        seed: The random seed to use for the search.
        time_limit_s: The time limit in seconds for the search.

    Returns:
        The solution dictionary with the routes and metadata.
    """
    # Set the random seed
    random.seed(seed)

    # Initialize the vehicle and charging components
    vehicle = instance.vehicle
    charging_component = ChargingComponent(instance)

    # Initialize the search control
    search_control = SearchControl(instance, vehicle, charging_component)

    # Run the search
    routes, metadata = search_control.search(time_limit_s)

    # Return the solution dictionary
    return {"routes": routes, "metadata": metadata}

class ChargingComponent:
    """
    The charging component of the EVRPTW solver.
    """

    def __init__(self, instance: EVRPTWInstance):
        """
        Initialize the charging component with the EVRPTW instance.

        Args:
            instance: The EVRPTW instance.
        """
        self.instance = instance

    def charge(self, vehicle: VehicleSpec, battery_on_arrival: float) -> ChargeDecision:
        """
        Charge the vehicle at the current node.

        Args:
            vehicle: The vehicle to charge.
            battery_on_arrival: The battery level at the current node.

        Returns:
            The charge decision.
        """
        # Calculate the energy required to travel to the next node
        energy_required = energy_required(vehicle, self.instance.node_map[vehicle.current_node_id], vehicle.current_node_id)

        # Check if the vehicle can charge at the current node
        if vehicle.battery_level >= energy_required:
            # Calculate the duration of the charge
            duration = full_recharge(vehicle, battery_on_arrival).duration

            # Update the vehicle's battery level and departure time
            vehicle.battery_level -= energy_required
            vehicle.battery_departure = self.instance.node_map[vehicle.current_node_id].due_time

            # Return the charge decision
            return ChargeDecision(energy_charged=energy_required, duration=duration, battery_departure=vehicle.battery_departure)
        else:
            # Return the charge decision
            return ChargeDecision(energy_charged=0, duration=0, battery_departure=vehicle.battery_departure)

class SearchControl:
    """
    The search control of the EVRPTW solver.
    """

    def __init__(self, instance: EVRPTWInstance, vehicle: VehicleSpec, charging_component: ChargingComponent):
        """
        Initialize the search control with the EVRPTW instance, vehicle, and charging component.

        Args:
            instance: The EVRPTW instance.
            vehicle: The vehicle.
            charging_component: The charging component.
        """
        self.instance = instance
        self.vehicle = vehicle
        self.charging_component = charging_component

    def search(self, time_limit_s: float) -> tuple[list[list[str]], dict]:
        """
        Search for a solution to the EVRPTW instance.

        Args:
            time_limit_s: The time limit in seconds for the search.

        Returns:
            The solution dictionary with the routes and metadata.
        """
        # Initialize the routes and metadata
        routes = []
        metadata = {"feasibility": "unknown", "vehicles": "unknown", "distance": "unknown"}

        # Initialize the current node and vehicle
        current_node_id = self.instance.depot_id
        current_vehicle = self.vehicle

        # Initialize the start time and battery level
        start_time = self.instance.node_map[current_node_id].ready_time
        battery_level = current_vehicle.battery_level

        # Initialize the route and the current node
        route = []
        current_node = self.instance.node_map[current_node_id]

        # While the current node is not the depot and the time limit has not been reached
        while current_node_id != self.instance.depot_id and start_time + time_limit_s > self.instance.node_map[current_node_id].due_time:
            # If the current node is a customer
            if current_node.kind == "customer":
                # Add the current node to the route
                route.append(current_node_id)

                # Update the current node and the battery level
                current_node = self.instance.node_map[current_node_id]
                battery_level -= energy_required(current_vehicle, current_node, current_node_id)

                # If the current node is the last customer
                if current_node_id == self.instance.customer_ids[-1]:
                    # Add the depot to the route
                    route.append(self.instance.depot_id)

                    # Update the metadata
                    metadata["feasibility"] = "feasible"
                    metadata["vehicles"] = 1
                    metadata["distance"] = distance(self.instance.node_map[self.instance.depot_id], self.instance.node_map[self.instance.customer_ids[-1]])

                    # Return the routes and metadata
                    return routes, metadata

                # If the current node is not the last customer
                else:
                    # Update the current node and the battery level
                    current_node = self.instance.node_map[current_node_id]
                    battery_level -= energy_required(current_vehicle, current_node, current_node_id)

            # If the current node is a station
            if current_node.kind == "station":
                # Charge the vehicle
                charge_decision = self.charging_component.charge(current_vehicle, battery_level)

                # Update the current node and the battery level
                current_node = self.instance.node_map[current_node_id]
                battery_level = charge_decision.battery_departure

            # Update the start time and the current node
            start_time = self.instance.node_map[current_node_id].due_time
            current_node_id = self.instance.node_map[current_node_id].next_node_id

        # If the current node is the depot
        if current_node_id == self.instance.depot_id:
            # Add the depot to the route
            route.append(self.instance.depot_id)

            # Update the metadata
            metadata["feasibility"] = "feasible"
            metadata["vehicles"] = 1
            metadata["distance"] = distance(self.instance.node_map[self.instance.depot_id], self.instance.node_map[self.instance.customer_ids[-1]])

            # Return the routes and metadata
            return routes, metadata

        # If the current node is not the depot
        else:
            # Update the metadata
            metadata["feasibility"] = "infeasible"
            metadata["vehicles"] = 0
            metadata["distance"] = 0

            # Return the routes and metadata
            return routes, metadata