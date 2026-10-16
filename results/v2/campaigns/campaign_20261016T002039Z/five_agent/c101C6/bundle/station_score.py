def station_score(detour: float, battery_arrival: float, station_rate: float) -> float:
    """Lower is better. Prefer reachable stations with short detour."""
    return detour + 0.1 * station_rate + (0.0 if battery_arrival > 0.0 else 1000.0)
