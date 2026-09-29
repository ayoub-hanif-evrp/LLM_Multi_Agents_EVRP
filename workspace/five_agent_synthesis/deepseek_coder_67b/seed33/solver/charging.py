from evrptw_autolab.problem.physics import energy_required, full_recharge, propagate_route

def greedy_charge(instance, route):
    """
    Greedy charging algorithm that tries to charge the vehicle at each stop in the route
    to full capacity before moving on to the next stop.
    """
    vehicle = instance.vehicle
    current_soc = vehicle.start_soc
    for i in range(len(route) - 1):
        a = route[i]
        b = route[i + 1]
        energy_to_consume = energy_required(a, b, vehicle)
        while energy_to_consume > 0:
            energy_to_consume -= vehicle.consumption_rate
            current_soc -= 1 / vehicle.inverse_refuel_rate
            if current_soc <= 0:
                current_soc = vehicle.battery_capacity
                vehicle.start_soc = current_soc
                full_recharge(vehicle, current_soc)
    return route

def charge_at_stations(instance, route):
    """
    Charging algorithm that tries to charge the vehicle at each station.
    """
    vehicle = instance.vehicle
    current_soc = vehicle.start_soc
    for stop_id in route:
        if stop_id in instance.station_ids:
            full_recharge(vehicle, current_soc)
            current_soc = vehicle.battery_capacity
            vehicle.start_soc = current_soc
    return route