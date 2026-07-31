"""Lexicographic objective vector (project-declared until contract resolves official obj)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ObjectiveVector(BaseModel):
    infeasibility_count: int = 0
    unserved_customers: int = 0
    vehicles_used: int = 0
    total_primary_cost: float = 0.0
    total_distance: float = 0.0
    total_travel_time: float = 0.0
    total_charging_time: float = 0.0
    definition: str = Field(
        default=(
            "project_declared_lexicographic:"
            "infeasibility,unserved,vehicles,primary_cost=distance,"
            "distance,travel_time,charging_time"
        )
    )

    def as_tuple(self) -> tuple[float | int, ...]:
        return (
            self.infeasibility_count,
            self.unserved_customers,
            self.vehicles_used,
            self.total_primary_cost,
            self.total_distance,
            self.total_travel_time,
            self.total_charging_time,
        )

    def dominates(self, other: ObjectiveVector) -> bool:
        a = self.as_tuple()
        b = other.as_tuple()
        weakly_better = all(x <= y for x, y in zip(a, b, strict=True))
        strictly_better = any(x < y for x, y in zip(a, b, strict=True))
        return weakly_better and strictly_better
