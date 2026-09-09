"""Immutable EVRPTW data types. No search or construction logic lives here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

NodeKind = Literal["depot", "customer", "station"]


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    kind: NodeKind
    x: float
    y: float
    demand: float = 0.0
    ready_time: float = 0.0
    due_time: float = float("inf")
    service_time: float = 0.0


@dataclass(frozen=True, slots=True)
class VehicleSpec:
    capacity: float
    battery_capacity: float
    consumption_rate: float
    velocity: float
    inverse_refuel_rate: float
    initial_soc: float | None = None

    @property
    def start_soc(self) -> float:
        return self.battery_capacity if self.initial_soc is None else self.initial_soc


@dataclass(frozen=True, slots=True)
class EVRPTWInstance:
    instance_id: str
    nodes: tuple[Node, ...]
    vehicle: VehicleSpec
    depot_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def node_map(self) -> dict[str, Node]:
        return {node.id: node for node in self.nodes}

    @property
    def depot(self) -> Node:
        return self.node_map[self.depot_id]

    @property
    def customer_ids(self) -> tuple[str, ...]:
        return tuple(n.id for n in self.nodes if n.kind == "customer")

    @property
    def n_customers(self) -> int:
        """Convenience alias used by generated solvers; same as len(customer_ids)."""
        return len(self.customer_ids)

    @property
    def customers(self) -> tuple[Node, ...]:
        return tuple(n for n in self.nodes if n.kind == "customer")

    @property
    def station_ids(self) -> tuple[str, ...]:
        return tuple(n.id for n in self.nodes if n.kind == "station")

    @property
    def stations(self) -> tuple[Node, ...]:
        return tuple(n for n in self.nodes if n.kind == "station")


@dataclass
class CandidateSolution:
    """Stable interface returned by a generated solver."""

    routes: list[list[str]]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationReport:
    parse_ok: bool = True
    feasible: bool = False
    all_customers_served_once: bool = False
    unserved: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    capacity_violations: int = 0
    time_window_violations: int = 0
    battery_violations: int = 0
    charging_violations: int = 0
    depot_violations: int = 0
    vehicles: int = 0
    total_distance: float = 0.0
    charging_visits: int = 0
    runtime_s: float = 0.0
    crashed: bool = False
    timed_out: bool = False
    error: str = ""
    first_fault: dict[str, Any] = field(default_factory=dict)
    routes: list[list[str]] = field(default_factory=list)
