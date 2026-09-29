import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.types import EVRPTWInstance, Node, VehicleSpec, StopState, ChargeDecision

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> dict:
    """
    Solve the EVRPTW instance using a routing, charging, search, and critic role.

    Args:
        instance: The EVRPTW instance to solve.
        seed: The random seed to use for the search.
        time_limit_s: The time limit in seconds for the search.

    Returns:
        A dictionary containing the routes and metadata for the solution.
    """
    # Set the random seed for reproducibility
    random.seed(seed)

    # Initialize the vehicle and charging state
    vehicle = instance.vehicle
    battery_state = vehicle.start_soc

    # Initialize the search state
    search_state = {
        "routes": [],
        "vehicle": vehicle,
        "battery_state": battery_state,
        "time_limit_s": time_limit_s,
        "seed": seed,
    }

    # Perform the search
    search_state = search(search_state, instance)

    # Extract the routes and metadata from the search state
    routes = search_state["routes"]
    metadata = {
        "feasibility": search_state["feasibility"],
        "vehicles": search_state["vehicles"],
        "distance": search_state["distance"],
    }

    # Return the routes and metadata
    return {"routes": routes, "metadata": metadata}

def search(search_state: dict, instance: EVRPTWInstance) -> dict:
    """
    Perform a search for a solution to the EVRPTW instance.

    Args:
        search_state: The current search state.
        instance: The EVRPTW instance to solve.

    Returns:
        The updated search state.
    """
    # Initialize the search state
    routes = search_state["routes"]
    vehicle = search_state["vehicle"]
    battery_state = search_state["battery_state"]
    time_limit_s = search_state["time_limit_s"]
    seed = search_state["seed"]

    # Perform the search
    while time_limit_s > 0 and len(routes) < instance.n_customers:
        # Generate a random route
        route = generate_route(instance, seed)

        # Check if the route is feasible
        feasibility = check_feasibility(instance, route, vehicle, battery_state)
        if feasibility:
            # Add the route to the list of routes
            routes.append(route)

            # Update the vehicle and charging state
            vehicle = update_vehicle(instance, route, vehicle)
            battery_state = update_battery_state(instance, route, battery_state)

            # Update the search state
            search_state["routes"] = routes
            search_state["vehicle"] = vehicle
            search_state["battery_state"] = battery_state

            # Update the time limit
            time_limit_s = time_limit_s - 1

    # Return the updated search state
    return search_state

def generate_route(instance: EVRPTWInstance, seed: int) -> list[str]:
    """
    Generate a random route for the EVRPTW instance.

    Args:
        instance: The EVRPTW instance to solve.
        seed: The random seed to use for the search.

    Returns:
        A list of node ids for the generated route.
    """
    # Initialize the route
    route = []

    # Add the depot to the route
    route.append(instance.depot_id)

    # Generate a random sequence of customer ids
    customer_ids = random.sample(instance.customer_ids, instance.n_customers - 1)

    # Add the customer ids to the route
    route.extend(customer_ids)

    # Add the depot to the end of the route
    route.append(instance.depot_id)

    # Return the generated route
    return route

def check_feasibility(instance: EVRPTWInstance, route: list[str], vehicle: VehicleSpec, battery_state: float) -> bool:
    """
    Check if the given route is feasible for the EVRPTW instance.

    Args:
        instance: The EVRPTW instance to solve.
        route: The route to check.
        vehicle: The vehicle to use for the check.
        battery_state: The battery state to use for the check.

    Returns:
        True if the route is feasible, False otherwise.
    """
    # Initialize the feasibility flag
    feasibility = True

    # Iterate over the route
    for i in range(len(route) - 1):
        # Get the current and next node ids
        current_node_id = route[i]
        next_node_id = route[i + 1]

        # Get the current and next nodes
        current_node = instance.node_map[current_node_id]
        next_node = instance.node_map[next_node_id]

        # Check if the current node is a customer
        if current_node.kind == "customer":
            # Check if the next node is a customer
            if next_node.kind == "customer":
                # Check if the current node is the same as the next node
                if current_node_id == next_node_id:
                    # The route is not feasible
                    return False

                # Get the distance between the current and next nodes
                distance = distance(current_node, next_node)

                # Check if the distance is greater than the vehicle's capacity
                if distance > vehicle.capacity:
                    # The route is not feasible
                    return False

                # Get the travel time between the current and next nodes
                travel_time = travel_time(current_node, next_node, vehicle)

                # Check if the travel time is greater than the vehicle's time window
                if travel_time > vehicle.time_window:
                    # The route is not feasible
                    return False

                # Get the energy required to travel between the current and next nodes
                energy_required = energy_required(current_node, next_node, vehicle)

                # Check if the energy required is greater than the vehicle's battery capacity
                if energy_required > vehicle.battery_capacity:
                    # The route is not feasible
                    return False

    # Return the feasibility flag
    return feasibility

def update_vehicle(instance: EVRPTWInstance, route: list[str], vehicle: VehicleSpec) -> VehicleSpec:
    """
    Update the vehicle state for the given route.

    Args:
        instance: The EVRPTW instance to solve.
        route: The route to update the vehicle state for.
        vehicle: The vehicle to update.

    Returns:
        The updated vehicle state.
    """
    # Initialize the updated vehicle
    updated_vehicle = vehicle

    # Iterate over the route
    for i in range(len(route) - 1):
        # Get the current and next node ids
        current_node_id = route[i]
        next_node_id = route[i + 1]

        # Get the current and next nodes
        current_node = instance.node_map[current_node_id]
        next_node = instance.node_map[next_node_id]

        # Check if the current node is a customer
        if current_node.kind == "customer":
            # Check if the next node is a customer
            if next_node.kind == "customer":
                # Check if the current node is the same as the next node
                if current_node_id == next_node_id:
                    # The route is not feasible
                    return None

                # Get the distance between the current and next nodes
                distance = distance(current_node, next_node)

                # Update the vehicle's capacity
                updated_vehicle.capacity = updated_vehicle.capacity - distance

                # Get the travel time between the current and next nodes
                travel_time = travel_time(current_node, next_node, vehicle)

                # Update the vehicle's time window
                updated_vehicle.time_window = updated_vehicle.time_window - travel_time

                # Get the energy required to travel between the current and next nodes
                energy_required = energy_required(current_node, next_node, vehicle)

                # Update the vehicle's battery capacity
                updated_vehicle.battery_capacity = updated_vehicle.battery_capacity - energy_required

    # Return the updated vehicle state
    return updated_vehicle

def update_battery_state(instance: EVRPTWInstance, route: list[str], battery_state: float) -> float:
    """
    Update the battery state for the given route.

    Args:
        instance: The EVRPTW instance to solve.
        route: The route to update the battery state for.
        battery_state: The battery state to update.

    Returns:
        The updated battery state.
    """
    # Initialize the updated battery state
    updated_battery_state = battery_state

    # Iterate over the route
    for i in range(len(route) - 1):
        # Get the current and next node ids
        current_node_id = route[i]
        next_node_id = route[i + 1]

        # Get the current and next nodes
        current_node = instance.node_map[current_node_id]
        next_node = instance.node_map[next_node_id]

        # Check if the current node is a customer
        if current_node.kind == "customer":
            # Check if the next node is a customer
            if next_node.kind == "customer":
                # Check if the current node is the same as the next node
                if current_node_id == next_node_id:
                    # The route is not feasible
                    return None

                # Get the distance between the current and next nodes
                distance = distance(current_node, next_node)

                # Get the travel time between the current and next nodes
                travel_time = travel_time(current_node, next_node, vehicle)

                # Get the energy required to travel between the current and next nodes
                energy_required = energy_required(current_node, next_node, vehicle)

                # Update the battery state
                updated_battery_state = updated_battery_state - energy_required

    # Return the updated battery state
    return updated_battery_state