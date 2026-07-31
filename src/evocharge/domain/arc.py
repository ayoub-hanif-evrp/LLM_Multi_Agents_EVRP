from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ArcMetrics:
    distance: float
    travel_time: float
    energy: float
    reachable: bool
