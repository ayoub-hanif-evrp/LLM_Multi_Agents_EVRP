def insertion_score(delta_distance: float, due_time: float, ready_time: float, demand: float, capacity_slack: float) -> float:
    return delta_distance + 0.01 * max(0, due_time - ready_time) + 0.1 * demand / max(1, capacity_slack)
