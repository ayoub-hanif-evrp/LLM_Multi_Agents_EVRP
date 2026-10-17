def removal_priority(due_time: float, route_distance_share: float, rng_value: float) -> float:
    return due_time - 1000000.0 * (1.0 - min(1.0, route_distance_share)) + 1000.0 * rng_value
