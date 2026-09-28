import numpy as np

def charge_vehicle(vehicle, battery_level):
    """
    Charges the vehicle's battery to a given level.

    Parameters:
        vehicle (Vehicle): The vehicle to be charged.
        battery_level (float): The desired battery level for the vehicle.
    """
    # Calculate the amount of energy required to charge the vehicle to the desired battery level
    energy_required = np.abs(battery_level - vehicle.battery_level) * vehicle.energy_per_unit
    
    # Check if the vehicle has enough energy to be charged to the desired battery level
    if energy_required > vehicle.battery:
        raise ValueError("Insufficient energy in vehicle's battery")
    
    # Charge the vehicle's battery to the desired level
    vehicle.battery += energy_required
    vehicle.battery_level = battery_level