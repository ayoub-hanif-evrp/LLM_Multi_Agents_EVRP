def removal_priority(due_time: float, route_distance_share: float, rng_value: float) -> float:
    """Higher means remove sooner."""
    return float(due_time) + 10.0 * float(route_distance_share) + 0.01 * float(rng_value)
