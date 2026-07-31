from __future__ import annotations

from pydantic import BaseModel, Field


class FeasibilityReport(BaseModel):
    feasible: bool
    missing_customers: list[str] = Field(default_factory=list)
    duplicate_customers: list[str] = Field(default_factory=list)
    invalid_node_visits: list[dict] = Field(default_factory=list)
    capacity_violations: list[dict] = Field(default_factory=list)
    time_window_violations: list[dict] = Field(default_factory=list)
    battery_violations: list[dict] = Field(default_factory=list)
    charging_violations: list[dict] = Field(default_factory=list)
    station_policy_violations: list[dict] = Field(default_factory=list)
    depot_violations: list[dict] = Field(default_factory=list)
    unreachable_arcs: list[dict] = Field(default_factory=list)
    numerical_warnings: list[str] = Field(default_factory=list)

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
            + len(self.station_policy_violations)
            + len(self.depot_violations)
            + len(self.unreachable_arcs)
        )
