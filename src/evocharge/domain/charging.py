"""Charging model strategies selected by dataset contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from evocharge.domain.vehicle import Vehicle


@dataclass(frozen=True, slots=True)
class ChargingDecision:
    energy_charged: float
    duration: float
    battery_on_departure: float


class ChargingModel(Protocol):
    def charging_duration(
        self,
        vehicle: Vehicle,
        battery_on_arrival: float,
        energy_charged: float,
    ) -> float: ...

    def validate_decision(
        self,
        vehicle: Vehicle,
        battery_on_arrival: float,
        energy_charged: float,
    ) -> list[str]: ...

    def full_recharge(
        self,
        vehicle: Vehicle,
        battery_on_arrival: float,
    ) -> ChargingDecision: ...


@dataclass(frozen=True, slots=True)
class LinearFullRechargeModel:
    """Provisional linear full-recharge model for Schneider Solomon EVRPTW.

    Duration uses inverse refuel rate ``g`` when available:
    ``duration = (Q - battery_arrival) * g``.
    If ``g`` is missing but ``gv`` (charging speed) is present:
    ``duration = (Q - battery_arrival) / gv``.
    Partial recharge is not claimed as official; callers may still
    request a specific energy amount for experimental schedules.
    """

    prefer_inverse_rate: bool = True

    def charging_duration(
        self,
        vehicle: Vehicle,
        battery_on_arrival: float,
        energy_charged: float,
    ) -> float:
        energy = max(0.0, energy_charged)
        if energy <= 0.0:
            return 0.0
        if self.prefer_inverse_rate and vehicle.inverse_refuel_rate is not None:
            return energy * float(vehicle.inverse_refuel_rate)
        if vehicle.charging_speed is not None and vehicle.charging_speed > 0.0:
            return energy / float(vehicle.charging_speed)
        if vehicle.inverse_refuel_rate is not None:
            return energy * float(vehicle.inverse_refuel_rate)
        raise ValueError("No charging rate parameters available on vehicle")

    def validate_decision(
        self,
        vehicle: Vehicle,
        battery_on_arrival: float,
        energy_charged: float,
    ) -> list[str]:
        errors: list[str] = []
        if energy_charged < -1e-9:
            errors.append("negative_energy_charged")
        if battery_on_arrival < -1e-9:
            errors.append("negative_battery_on_arrival")
        if battery_on_arrival + energy_charged > vehicle.battery_capacity + 1e-6:
            errors.append("exceeds_battery_capacity")
        try:
            self.charging_duration(vehicle, battery_on_arrival, energy_charged)
        except ValueError as exc:
            errors.append(str(exc))
        return errors

    def full_recharge(
        self,
        vehicle: Vehicle,
        battery_on_arrival: float,
    ) -> ChargingDecision:
        energy = max(0.0, vehicle.battery_capacity - battery_on_arrival)
        duration = self.charging_duration(vehicle, battery_on_arrival, energy)
        return ChargingDecision(
            energy_charged=energy,
            duration=duration,
            battery_on_departure=battery_on_arrival + energy,
        )


def default_charging_model() -> LinearFullRechargeModel:
    return LinearFullRechargeModel(prefer_inverse_rate=True)
