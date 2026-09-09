import numpy as np

def charge_vehicle(vehicle, battery_on_arrival):
    """
    Charges the vehicle's battery to full capacity.

    Parameters:
        vehicle (Vehicle): The vehicle to be charged.
        battery_on_arrival (float): The initial battery level of the vehicle at its arrival time.

    Returns:
        float: The new battery level of the vehicle after charging.
    """
    # Calculate the amount of energy required to charge the vehicle's battery to full capacity.
    energy_required = vehicle.battery_capacity - battery_on_arrival

    # Charging rate is a constant and does not depend on the vehicle's current speed or any other factors.
    charging_rate = 0.5

    # Calculate the new battery level of the vehicle after charging.
    new_battery_level = np.clip(battery_on_arrival + energy_required * charging_rate, 0, vehicle.battery_capacity)

    return new_battery_level