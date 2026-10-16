def removal_priority(due_time: float, route_distance_share: float, rng_value: float) -> float:
    """Higher means remove sooner. Ignore sentinel dues (1e6)."""
    return (0.0 if due_time >= 1000000.0 else due_time) + 10.0 * route_distance_share + 0.01 * rng_value
