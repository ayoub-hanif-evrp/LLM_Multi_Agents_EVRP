from evrptw_autolab.problem.physics import distance, energy_required, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    depot = instance.depot_id
    routes = []
    metadata = {"seed": seed}

    for cid in instance.customer_ids:
        route = [depot, cid, depot]
        states = propagate_route(instance, route)

        if any(state.battery_arrival < 0 for state in states):
            # Insert stations to repair the route
            k = 1
            while k < len(route) - 1 and states[k].battery_arrival >= 0:
                k += 1

            station_ids = instance.station_ids
            best_station = None
            min_lateness = float('inf')

            for station_id in station_ids:
                new_route = route[:k] + [station_id] + route[k:]
                new_states = propagate_route(instance, new_route)
                if all(state.battery_arrival >= 0 for state in new_states):
                    lateness = new_states[-1].arrival_time - instance.node_map[new_states[-2].node_id].due_time
                    if lateness < min_lateness:
                        min_lateness = lateness
                        best_station = station_id

            if best_station is not None:
                route = route[:k] + [best_station] + route[k:]

        # Ensure the return to depot is within due time
        final_state = propagate_route(instance, route)[-1]
        if final_state.arrival_time > instance.node_map[depot].due_time:
            # Check if the route without this station is still battery-feasible
            new_route = route[:-2] + [depot]
            new_states = propagate_route(instance, new_route)
            if all(state.battery_arrival >= 0 for state in new_states):
                route = new_route

        routes.append(route)

    return {"routes": routes, "metadata": metadata}