import math

def solve(instance, seed, time_limit_s):
    # Initialize the routing algorithm
    routes = []
    visited_customers = set()

    # Iterate through each customer
    for customer_id in instance.customer_ids:
        # If the customer has already been visited, skip it
        if customer_id in visited_customers:
            continue

        # Add the customer to the visited customers set
        visited_customers.add(customer_id)

        # Initialize the current route
        current_route = [instance.depot_id]

        # Iterate through each vehicle
        for vehicle in instance.vehicles:
            # If the vehicle is not available, skip it
            if vehicle.capacity < instance.customers[customer_id].demand:
                continue

            # Add the customer to the current route
            current_route.append(customer_id)

            # If the current route is not feasible, skip it
            if not is_feasible(instance, current_route):
                continue

            # If the current route is not the shortest, skip it
            if len(current_route) < len(routes) or (len(current_route) == len(routes) and distance(instance, current_route) < distance(instance, routes)):
                continue

            # Add the current route to the routes list
            routes.append(current_route)

    # Return the routes
    return {"routes": routes}

def is_feasible(instance, route):
    # Initialize the current vehicle
    current_vehicle = instance.vehicle

    # Iterate through each stop in the route
    for i in range(len(route) - 1):
        # If the stop is a customer, add the customer demand to the current vehicle's capacity
        if route[i] in instance.customers:
            current_vehicle.capacity += instance.customers[route[i]].demand

        # If the stop is a station, subtract the station's consumption rate from the current vehicle's capacity
        elif route[i] in instance.stations:
            current_vehicle.capacity -= instance.stations[route[i]].consumption_rate

        # If the current vehicle's capacity is less than zero, return False
        if current_vehicle.capacity < 0:
            return False

    # Return True if the route is feasible
    return True

def distance(instance, route):
    # Initialize the total distance
    total_distance = 0

    # Iterate through each stop in the route
    for i in range(len(route) - 1):
        # Add the distance between the current stop and the next stop to the total distance
        total_distance += distance(instance, route[i], route[i + 1])

    # Return the total distance
    return total_distance

def distance(instance, a, b):
    # Return the Euclidean distance between the two nodes
    return math.sqrt((instance.nodes[a].x - instance.nodes[b].x) ** 2 + (instance.nodes[a].y - instance.nodes[b].y) ** 2)