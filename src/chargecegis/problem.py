"""Core immutable domain types for the Schneider EVRPTW benchmark."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

NodeKind = Literal["depot", "customer", "station"]


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    kind: NodeKind
    coordinates: tuple[float, float]
    demand: float = 0.0
    service_duration: float = 0.0
    ready_time: float = 0.0
    due_time: float = float("inf")
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Vehicle:
    freight_capacity: float
    battery_capacity: float
    initial_soc: float
    consumption_rate: float
    velocity: float
    inverse_refuel_rate: float
    terminal_soc_min: float = 0.0


@dataclass(frozen=True, slots=True)
class Instance:
    instance_id: str
    dataset_name: str
    nodes: Mapping[str, Node]
    depot_id: str
    customer_ids: tuple[str, ...]
    station_ids: tuple[str, ...]
    vehicle: Vehicle
    horizon: float
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def depot(self) -> Node:
        return self.nodes[self.depot_id]


@dataclass(frozen=True, slots=True)
class ArcMetrics:
    distance: float
    travel_time: float
    energy: float
    reachable: bool


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


@dataclass(frozen=True, slots=True)
class Route:
    vehicle_index: int
    node_ids: tuple[str, ...]
    schedule: tuple[ScheduleStop, ...] = ()


@dataclass(frozen=True, slots=True)
class Solution:
    routes: tuple[Route, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, order=True)
class ObjectiveVector:
    infeasibility_count: int = 0
    unserved_customers: int = 0
    vehicles_used: int = 0
    total_distance: float = 0.0
    total_travel_time: float = 0.0
    total_charging_time: float = 0.0

    def as_tuple(self) -> tuple[int | float, ...]:
        return (
            self.infeasibility_count, self.unserved_customers, self.vehicles_used,
            self.total_distance, self.total_travel_time, self.total_charging_time,
        )


@dataclass
class FeasibilityReport:
    feasible: bool = False
    missing_customers: list[str] = field(default_factory=list)
    duplicate_customers: list[str] = field(default_factory=list)
    invalid_node_visits: list[dict[str, Any]] = field(default_factory=list)
    capacity_violations: list[dict[str, Any]] = field(default_factory=list)
    time_window_violations: list[dict[str, Any]] = field(default_factory=list)
    battery_violations: list[dict[str, Any]] = field(default_factory=list)
    charging_violations: list[dict[str, Any]] = field(default_factory=list)
    depot_violations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def violation_count(self) -> int:
        return (
            len(self.missing_customers)
            + len(self.duplicate_customers)
            + len(self.invalid_node_visits)
            + len(self.capacity_violations)
            + len(self.time_window_violations)
            + len(self.battery_violations)
            + len(self.charging_violations)
            + len(self.depot_violations)
        )
