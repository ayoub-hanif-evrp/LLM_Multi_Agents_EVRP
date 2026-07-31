"""Typed results and context for operators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evocharge.domain.instance import Instance
from evocharge.domain.solution import Solution
from evocharge.solver.charging_repair import ChargingRepairCache, RepairBounds
from evocharge.solver.profiling import Profiler


@dataclass
class OperatorContext:
    instance: Instance
    cache: ChargingRepairCache
    destroy_fraction: float = 0.2
    repair_bounds: RepairBounds = field(default_factory=RepairBounds)
    profiler: Profiler | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DestroyResult:
    solution: Solution
    removed_customers: tuple[str, ...]
    operator: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RepairResult:
    solution: Solution
    inserted_customers: tuple[str, ...]
    unserved: tuple[str, ...]
    operator: str
    rejection_reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
