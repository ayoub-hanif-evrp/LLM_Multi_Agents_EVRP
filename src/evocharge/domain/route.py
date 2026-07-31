from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ScheduleStop:
    node_id: str
    traveled_distance: float
    arrival_time: float
    waiting_time: float
    service_start: float
    service_completion: float
    departure_time: float
    cumulative_load: float
    battery_on_arrival: float
    energy_charged: float
    battery_on_departure: float
    energy_required_next: float | None
    time_slack: float
    energy_slack: float
    charging_duration: float
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Route:
    vehicle_index: int
    node_ids: tuple[str, ...]
    schedule: tuple[ScheduleStop, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def customer_ids(self, instance_customer_ids: set[str]) -> tuple[str, ...]:
        return tuple(nid for nid in self.node_ids if nid in instance_customer_ids)
