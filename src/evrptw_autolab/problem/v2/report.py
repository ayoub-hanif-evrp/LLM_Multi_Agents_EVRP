"""Rich evaluation reports for the VoltForge 2.0 oracle (no LLM)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class StopStateV2:
    node_id: str
    arrival_time: float
    service_start: float
    departure_time: float
    load: float
    battery_arrival: float
    battery_departure: float
    energy_charged: float
    distance_so_far: float
    charge_technology: str | None = None


@dataclass
class ViolationV2:
    family: str
    node_id: str = ""
    route_index: int = -1
    detail: str = ""
    magnitude: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluationReportV2:
    feasible: bool = False
    parse_ok: bool = True
    objective: float | None = None
    objective_components: dict[str, float] = field(default_factory=dict)
    vehicles: int = 0
    total_distance: float = 0.0
    total_duration: float = 0.0
    charging_visits: int = 0
    unserved: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    violations: list[ViolationV2] = field(default_factory=list)
    first_fault: ViolationV2 | None = None
    trajectories: list[list[StopStateV2]] = field(default_factory=list)
    runtime_s: float = 0.0
    error: str = ""
    family: str = ""
    explanation: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["first_fault"] = self.first_fault.as_dict() if self.first_fault else None
        payload["violations"] = [v.as_dict() for v in self.violations]
        return payload

    def add(self, family: str, *, node_id: str = "", route_index: int = -1, detail: str = "", magnitude: float = 0.0) -> None:
        fault = ViolationV2(family, node_id, route_index, detail, magnitude)
        self.violations.append(fault)
        if self.first_fault is None:
            self.first_fault = fault
