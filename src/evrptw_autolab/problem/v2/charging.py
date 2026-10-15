"""Charging duration models: linear full/partial, nonlinear piecewise, multi-tech."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evrptw_autolab.problem.v2.transport import EPSILON
from evrptw_autolab.problem.v2.types import NodeV2, ProblemSpecV2, RouteStopV2, VehicleTypeV2


@dataclass(frozen=True, slots=True)
class ChargeResult:
    energy_charged: float
    duration: float
    battery_departure: float
    technology: str | None
    errors: tuple[str, ...] = ()


def _interp_charge_time(breakpoints: list[dict[str, float]], battery_level: float) -> float:
    """Map battery level → cumulative charging time on a monotone piecewise-linear curve."""
    if not breakpoints:
        raise ValueError("empty charging breakpoints")
    pts = sorted(breakpoints, key=lambda p: p["battery_level"])
    b = max(pts[0]["battery_level"], min(battery_level, pts[-1]["battery_level"]))
    for i in range(1, len(pts)):
        b0, t0 = pts[i - 1]["battery_level"], pts[i - 1]["charging_time"]
        b1, t1 = pts[i]["battery_level"], pts[i]["charging_time"]
        if b <= b1 + EPSILON:
            if abs(b1 - b0) < EPSILON:
                return t1
            ratio = (b - b0) / (b1 - b0)
            return t0 + ratio * (t1 - t0)
    return pts[-1]["charging_time"]


def nonlinear_charge_duration(
    breakpoints: list[dict[str, float]],
    battery_arrival: float,
    battery_target: float,
) -> float:
    if battery_target + EPSILON < battery_arrival:
        raise ValueError("nonlinear charge target below arrival SoC")
    return max(
        0.0,
        _interp_charge_time(breakpoints, battery_target)
        - _interp_charge_time(breakpoints, battery_arrival),
    )


def resolve_charge(
    spec: ProblemSpecV2,
    vehicle: VehicleTypeV2,
    station: NodeV2,
    stop: RouteStopV2,
    battery_arrival: float,
) -> ChargeResult:
    """Compute charge energy/duration at a station stop. Never calls an LLM."""
    errors: list[str] = []
    caps = spec.capabilities
    battery_cap = vehicle.battery_capacity
    if battery_cap is None:
        return ChargeResult(0.0, 0.0, battery_arrival, None, ("no_battery_on_vehicle",))

    if battery_arrival < -EPSILON:
        errors.append("negative_battery_on_arrival")

    # Target SoC / energy.
    if stop.target_soc is not None:
        target = float(stop.target_soc)
    elif stop.charge_amount is not None:
        target = battery_arrival + float(stop.charge_amount)
    else:
        target = float(battery_cap)  # default: charge to full

    if target > float(battery_cap) + EPSILON:
        errors.append("charge_above_capacity")
        target = float(battery_cap)
    if target + EPSILON < battery_arrival and stop.charge_amount is not None and stop.charge_amount < 0:
        errors.append("negative_charge_amount")
        target = battery_arrival

    energy = max(0.0, target - battery_arrival)
    tech = stop.charge_technology

    # Technology compatibility (Bezzi / Montoya station types).
    if caps.multiple_charge_technologies or station.charge_technologies:
        allowed = set(station.charge_technologies)
        if allowed:
            if tech is None:
                # Default to the station's sole technology when unambiguous.
                if len(allowed) == 1:
                    tech = next(iter(allowed))
                else:
                    errors.append("missing_charge_technology")
            elif str(tech) not in allowed:
                errors.append(f"incompatible_technology:{tech}")

    duration = 0.0
    if energy <= EPSILON:
        return ChargeResult(0.0, 0.0, battery_arrival, tech, tuple(errors))

    if caps.nonlinear_charging:
        funcs: dict[str, Any] = {}
        meta_funcs = spec.metadata.get("charging_functions") or vehicle.metadata.get("charging_functions")
        if isinstance(meta_funcs, dict):
            funcs = meta_funcs
        cs_type = tech or (station.charge_technologies[0] if station.charge_technologies else None)
        if cs_type is None or cs_type not in funcs:
            errors.append(f"missing_nonlinear_curve:{cs_type}")
            return ChargeResult(energy, 0.0, target, tech, tuple(errors))
        try:
            duration = nonlinear_charge_duration(list(funcs[cs_type]), battery_arrival, target)
        except ValueError as error:
            errors.append(str(error))
            duration = 0.0
    elif caps.multiple_charge_technologies:
        tech_params = (vehicle.metadata.get("charging_techs") or {}).get(str(tech), {})
        # Bezzi-style: duration = energy * rho (inverse rate); rho=0 ⇒ instantaneous / free.
        rho = float(tech_params.get("rho", 0.0))
        duration = energy * rho
    else:
        # Linear full/partial using inverse_refuel_rate on vehicle metadata or station rate.
        inv = vehicle.metadata.get("inverse_refuel_rate")
        if inv is None and station.recharging_rate is not None:
            # Hiermann: rechargingrate column — treat as inverse rate (time per energy).
            inv = station.recharging_rate
        if inv is None:
            errors.append("missing_refuel_rate")
            inv = 0.0
        duration = energy * float(inv)
        if caps.full_recharge and not caps.partial_recharge:
            expected = max(0.0, float(battery_cap) - battery_arrival)
            if abs(energy - expected) > EPSILON:
                errors.append("partial_recharge_not_allowed")

    return ChargeResult(energy, duration, target, tech, tuple(errors))
