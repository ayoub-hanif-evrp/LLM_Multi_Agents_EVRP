def full_recharge(vehicle, battery_on_arrival: float) -> float:
    # Assuming a constant charging rate of 1 unit per second
    charge_rate = 1
    
    # Calculate energy required for recharge operation
    energy_required = vehicle.max_battery_capacity - battery_on_arrival
    
    # Calculate total time to fully charge the vehicle
    total_time = energy_required / charge_rate
    
    return total_time