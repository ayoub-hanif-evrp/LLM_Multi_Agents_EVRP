import random
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution

def charging_policy(instance, route):
    # Initialize the route with the depot
    current_node = instance.node_map[route[0]]
    current_battery = instance.vehicle.start_soc
    charged_routes = []

    for node_id in route[1:]:
        next_node = instance.node_map[node_id]
        energy_needed = energy_required(current_node, next_node, instance.vehicle)

        if current_battery < energy_needed:
            # Find the nearest station to recharge
            nearest_station = min(
                instance.stations,
                key=lambda station: distance(current_node, station)
            )

            # Calculate the energy required to reach the nearest station
            energy_to_station = energy_required(current_node, nearest_station)

            if current_battery >= energy_to_station:
                # If we can reach the station, go there and recharge
                charged_routes.append(nearest_station.id)
                charge_decision = full_recharge(instance.vehicle, current_battery - energy_to_station)
                current_battery = charge_decision.battery_departure
            else:
                # If we can't reach the station, the route is infeasible
                return None

        # Move to the next node
        charged_routes.append(next_node.id)
        current_battery -= energy_needed
        current_node = next_node

    return charged_routes

def solve(instance, seed: int, time_limit_s: float):
    random.seed(seed)

    def is_feasible(routes):
        candidate = CandidateSolution(routes=routes)
        fault = first_fault(instance, candidate)
        return fault["family"] == "OK"

    def generate_initial_routes():
        routes = []
        remaining_customers = list(instance.customer_ids)
        while remaining_customers:
            route = [instance.depot_id]
            current_node = instance.depot
            current_load = 0
            current_battery = instance.vehicle.start_soc

            while remaining_customers:
                next_customer = None
                for customer_id in remaining_customers:
                    customer = instance.node_map[customer_id]
                    if customer.demand + current_load <= instance.vehicle.capacity:
                        if current_battery - energy_required(current_node, customer, instance.vehicle) >= 0:
                            next_customer = customer
                            break

                if next_customer:
                    route.append(next_customer.id)
                    current_load += next_customer.demand
                    current_battery -= energy_required(current_node, next_customer, instance.vehicle)
                    current_node = next_customer
                    remaining_customers.remove(next_customer.id)
                else:
                    break

            route.append(instance.depot_id)
            routes.append(route)

        return routes

    def repair_routes(routes):
        # Basic repair logic: if a route is infeasible, try to split it
        for i, route in enumerate(routes):
            candidate = CandidateSolution(routes=[route])
            fault = first_fault(instance, candidate)
            if fault["family"] != "OK":
                # Split the route at the fault point
                split_index = fault["route_index"]
                routes[i] = route[:split_index + 1]
                routes.append(route[split_index + 1:])
                break

        return routes

    def local_search(routes):
        # Simple local search: try swapping two customers in different routes
        for _ in range(100):
            if len(routes) < 2:
                continue
            i, j = random.sample(range(len(routes)), 2)
            if len(routes[i]) > 2 and len(routes[j]) > 2:
                # Swap two customers
                customer_i = random.choice(routes[i][1:-1])
                customer_j = random.choice(routes[j][1:-1])

                routes[i].remove(customer_i)
                routes[j].remove(customer_j)

                routes[i].insert(random.randint(1, len(routes[i]) - 1), customer_j)
                routes[j].insert(random.randint(1, len(routes[j]) - 1), customer_i)

                if is_feasible(routes):
                    return routes

        return routes

    # Generate initial routes
    routes = generate_initial_routes()

    # Apply charging policy to each route
    charged_routes = []
    for route in routes:
        charged_route = charging_policy(instance, route)
        if charged_route:
            charged_routes.append(charged_route)
        else:
            # If a route is infeasible after charging, try to repair it
            charged_routes.append(repair_routes([route])[0])

    # Perform local search
    charged_routes = local_search(charged_routes)

    # Ensure all customers are visited
    all_customers = set(instance.customer_ids)
    visited_customers = set()
    for route in charged_routes:
        visited_customers.update(route[1:-1])

    if all_customers != visited_customers:
        # If any customer is missing, add a new route for them
        missing_customers = all_customers - visited_customers
        for customer_id in missing_customers:
            charged_routes.append([instance.depot_id, customer_id, instance.depot_id])

    # Ensure feasibility
    while not is_feasible(charged_routes):
        charged_routes = repair_routes(charged_routes)
        charged_routes = local_search(charged_routes)

    return {"routes": charged_routes, "metadata": {}}