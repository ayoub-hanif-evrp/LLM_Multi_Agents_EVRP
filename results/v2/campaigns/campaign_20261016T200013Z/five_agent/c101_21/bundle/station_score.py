def station_score(detour: float, battery_arrival: float, station_rate: float) -> float:
    return detour + 0.5 * battery_arrival + station_rate
