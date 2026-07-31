from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Vehicle:
    freight_capacity: float
    battery_capacity: float
    initial_soc: float
    terminal_soc_min: float = 0.0
    consumption_rate: float = 0.0
    velocity: float = 1.0
    inverse_refuel_rate: float | None = None
    charging_speed: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
