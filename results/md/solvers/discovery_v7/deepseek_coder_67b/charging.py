# charging.py

from typing import List, Dict
import random

class ChargingStation:
    def __init__(self, id: str):
        self.id = id
        self.vehicles_charging = 0

    def charge(self, vehicle):
        if self.vehicles_charging < 5:  # Assuming a maximum of 5 vehicles can be charged at once
            self.vehicles_charging += 1
            return True
        else:
            return False

class ChargingManager:
    def __init__(self, charging_stations: List[ChargingStation]):
        self.charging_stations = charging_stations

    def find_available_station(self) -> ChargingStation:
        for station in self.charging_stations:
            if station.vehicles_charging < 5:
                return station
        return None