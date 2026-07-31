"""Simulated annealing acceptance."""

from __future__ import annotations

import math
import random

from evocharge.domain.objective import ObjectiveVector


def accept_candidate(
    current: ObjectiveVector,
    candidate: ObjectiveVector,
    *,
    temperature: float,
    rng: random.Random,
) -> bool:
    if candidate.as_tuple() <= current.as_tuple():
        return True
    # Use primary cost difference for SA when both feasible-ish
    delta = candidate.total_primary_cost - current.total_primary_cost
    # If candidate has more infeasibility, reject unless temperature high and random
    if candidate.infeasibility_count > current.infeasibility_count:
        return False
    if temperature <= 1e-12:
        return False
    prob = math.exp(-max(delta, 0.0) / temperature)
    return rng.random() < prob


def cool(temperature: float, cooling_rate: float) -> float:
    return max(1e-12, temperature * cooling_rate)
