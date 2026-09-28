from evrptw_autolab.problem.physics import distance, energy_required, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    routes = []
    metadata = {}
    
    for customer_id in instance.customer_ids:
        route = [instance.depot_id, customer_id, instance.depot_id]
        states = propagate_route(instance, route)
        
        if states[-1].battery_arrival < 0:
            # Find a charging station to insert
            available_stations = instance.station_ids
            for station_id in available_stations:
                # Insert station before the customer
                new_route = [instance.depot_id, station_id, customer_id, instance.depot_id]
                new_states = propagate_route(instance, new_route)
                if new_states[-1].battery_arrival >= 0:
                    route = new_route
                    break
        
        routes.append(route)
    
    return {"routes": routes, "metadata": metadata}