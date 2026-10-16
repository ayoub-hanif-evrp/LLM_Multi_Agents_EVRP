def removal_priority(due_time: float, route_distance_share: float, rng_value: float) -> float:
    return due_time + 10.0 * route_distance_share + 0.01 * rng_value
