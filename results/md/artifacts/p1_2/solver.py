from evrptw_autolab.problem.physics import distance, energy_required, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    depot = instance.depot_id
    routes = []
    metadata = {"seed": seed}

    for cid in instance.customer_ids:
        route = [depot, cid, depot]
        states = propagate_route(instance, route)

        if any(state.battery_arrival < 0 or (hasattr(state, 'lateness') and state.lateness > 0) for state in states):
            # Insert stations to repair the route
            k = 1
            while k < len(route) - 1 and (states[k].battery_arrival >= 0 and (hasattr(states[k], 'lateness') and states[k].lateness <= 0)):
                k += 1

            available_station_ids = instance.station_ids
            for station_id in available_station_ids:
                new_route = route[:k] + [station_id] + route[k:]
                new_states = propagate_route(instance, new_route)
                if all(state.battery_arrival >= 0 and (hasattr(state, 'lateness') and state.lateness <= 0) for state in new_states):
                    route = new_route
                    break

        routes.append(route)

    return {"routes": routes, "metadata": metadata}