from evrptw_autolab.problem.physics import distance, energy_required, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    depot = instance.depot_id
    routes = []
    
    for cid in instance.customer_ids:
        route = [depot, cid, depot]
        states = propagate_route(instance, route)
        
        # Check if the route is battery-feasible
        if all(state.battery_arrival >= 0 for state in states):
            routes.append(route)
            continue
        
        # If not battery-feasible, insert a charging station
        for station_id in instance.station_ids:
            for i in range(1, len(route)):
                new_route = route[:i] + [station_id] + route[i:]
                new_states = propagate_route(instance, new_route)
                
                if all(state.battery_arrival >= 0 for state in new_states):
                    routes.append(new_route)
                    break
            else:
                continue
            break
    
    return {"routes": routes, "metadata": {"seed": seed}}