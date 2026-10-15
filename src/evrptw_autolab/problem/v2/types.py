"""Normalized immutable problem / solution types for multi-variant EVRP.

Legacy ``EVRPTWInstance`` remains the Schneider Experiment A/B contract.
Adapters convert between representations; this module must not mutate legacy types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ProblemFamily = Literal["schneider", "montoya", "bezzi", "goeke", "hiermann", "micro", "synthetic"]


@dataclass(frozen=True, slots=True)
class CapabilityFlags:
    """Explicit variant capabilities — prefer these over stringly-typed checks."""

    time_windows: bool = False
    capacity: bool = False
    battery: bool = False
    full_recharge: bool = False
    partial_recharge: bool = False
    nonlinear_charging: bool = False
    multiple_charge_technologies: bool = False
    pickup_delivery: bool = False
    heterogeneous_fleet: bool = False
    conventional_vehicles: bool = False
    hybrid_vehicles: bool = False
    matrix_distances: bool = False
    euclidean_distances: bool = True
    max_route_duration: bool = False
    station_revisits_allowed: bool = True


@dataclass(frozen=True, slots=True)
class VehicleTypeV2:
    type_id: str
    capacity: float
    battery_capacity: float | None = None
    consumption_rate: float | None = None
    velocity: float | None = None
    is_electric: bool = True
    is_conventional: bool = False
    is_hybrid: bool = False
    fixed_cost: float = 0.0
    variable_cost: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NodeV2:
    id: str
    kind: Literal["depot", "customer", "station", "pickup", "delivery"]
    x: float
    y: float
    demand: float = 0.0
    ready_time: float = 0.0
    due_time: float = float("inf")
    service_time: float = 0.0
    partner_id: str | None = None
    charge_technologies: tuple[str, ...] = ()
    recharging_rate: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RequestV2:
    """Pickup-delivery request when ``capabilities.pickup_delivery`` is true."""

    request_id: str
    pickup_id: str
    delivery_id: str
    demand: float
    same_vehicle: bool = True


@dataclass(frozen=True, slots=True)
class ProblemSpecV2:
    """General problem specification. Immutable once constructed for a run."""

    instance_id: str
    family: ProblemFamily
    capabilities: CapabilityFlags
    nodes: tuple[NodeV2, ...]
    vehicle_types: tuple[VehicleTypeV2, ...]
    depot_ids: tuple[str, ...]
    requests: tuple[RequestV2, ...] = ()
    fleet_availability: dict[str, int] = field(default_factory=dict)
    objective: str = "minimize_distance"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def node_map(self) -> dict[str, NodeV2]:
        return {n.id: n for n in self.nodes}


@dataclass(frozen=True, slots=True)
class RouteStopV2:
    node_id: str
    vehicle_type_id: str | None = None
    event: Literal["visit", "pickup", "delivery", "charge", "depot"] = "visit"
    charge_amount: float | None = None
    charge_technology: str | None = None
    target_soc: float | None = None


@dataclass
class SolutionV2:
    """Candidate solution. Evaluator recomputes physical state; timestamps here are diagnostic only."""

    routes: list[list[RouteStopV2]]
    vehicle_assignments: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_legacy_routes(
        routes: list[list[str]],
        *,
        vehicle_type_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SolutionV2:
        """Adapter for legacy ``list[list[str]]`` Schneider-style routes."""
        converted: list[list[RouteStopV2]] = []
        assignments: list[str] = []
        for route in routes:
            stops: list[RouteStopV2] = []
            for i, node_id in enumerate(route):
                if i == 0 or i == len(route) - 1:
                    event: Literal["visit", "pickup", "delivery", "charge", "depot"] = "depot"
                else:
                    event = "visit"
                stops.append(RouteStopV2(node_id=str(node_id), vehicle_type_id=vehicle_type_id, event=event))
            converted.append(stops)
            if vehicle_type_id:
                assignments.append(vehicle_type_id)
        return SolutionV2(routes=converted, vehicle_assignments=assignments, metadata=dict(metadata or {}))

    def to_legacy_routes(self) -> list[list[str]]:
        return [[stop.node_id for stop in route] for route in self.routes]


def schneider_capabilities() -> CapabilityFlags:
    return CapabilityFlags(
        time_windows=True,
        capacity=True,
        battery=True,
        full_recharge=True,
        euclidean_distances=True,
        station_revisits_allowed=True,
    )
