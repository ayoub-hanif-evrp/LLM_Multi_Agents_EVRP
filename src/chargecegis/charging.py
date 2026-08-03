"""The locked Schneider full-recharge charging policy."""
from __future__ import annotations

from dataclasses import dataclass

from chargecegis.problem import Vehicle

EPSILON = 1e-6


@dataclass(frozen=True, slots=True)
class ChargingDecision:
    energy_charged: float
    duration: float
    battery_on_departure: float


@dataclass(frozen=True, slots=True)
class LinearFullRechargeModel:
    """Schneider policy: every station departure has battery level ``Q``."""

    def charging_duration(
        self, vehicle: Vehicle, battery_on_arrival: float, energy_charged: float
    ) -> float:
        expected = max(0.0, vehicle.battery_capacity - battery_on_arrival)
        if abs(energy_charged - expected) > EPSILON:
            raise ValueError("partial_recharge_not_allowed")
        return expected * vehicle.inverse_refuel_rate

    def full_recharge(self, vehicle: Vehicle, battery_on_arrival: float) -> ChargingDecision:
        energy = max(0.0, vehicle.battery_capacity - battery_on_arrival)
        return ChargingDecision(energy, self.charging_duration(vehicle, battery_on_arrival, energy),
                                vehicle.battery_capacity)

    def validate_decision(
        self, vehicle: Vehicle, battery_on_arrival: float, energy_charged: float
    ) -> list[str]:
        errors: list[str] = []
        if battery_on_arrival < -EPSILON:
            errors.append("negative_battery_on_arrival")
        if abs(battery_on_arrival + energy_charged - vehicle.battery_capacity) > EPSILON:
            errors.append("station_must_depart_full")
        try:
            self.charging_duration(vehicle, battery_on_arrival, energy_charged)
        except ValueError as error:
            errors.append(str(error))
        return errors
