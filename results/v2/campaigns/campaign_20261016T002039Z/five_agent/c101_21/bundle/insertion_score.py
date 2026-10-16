def insertion_score(delta_distance: float, due_time: float, ready_time: float, demand: float, capacity_slack: float) -> float:
    """Lower is better. Single arithmetic return for the bounded interpreter."""
    return delta_distance + (0.0 if due_time >= 1000000.0 else (0.01 * due_time + 1.0 / max(due_time - ready_time, 1.0))) + (0.0 if capacity_slack >= demand else 1000000.0)
